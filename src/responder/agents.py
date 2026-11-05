"""Model clients (Claude for writing, Jev for decisions), prompts, Jev questions and cost tracking."""
from __future__ import annotations

import re
import threading
from collections import defaultdict

from .config import PRICES

# --------------------------------------------------------------------------- cost tracking

class Usage:
    """Thread-safe token counter per model, priced with config.PRICES."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.by_model = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0})

    def add(self, model: str, input_tokens: int | None, output_tokens: int | None):
        with self._lock:
            u = self.by_model[model]
            u["calls"] += 1
            u["input_tokens"] += input_tokens or 0
            u["output_tokens"] += output_tokens or 0

    def rows(self) -> list[dict]:
        out = []
        for model, u in dict(self.by_model).items():
            p_in, p_out = PRICES.get(model, (0, 0))
            out.append({"model": model, **u,
                        "cost_usd": u["input_tokens"] / 1e6 * p_in + u["output_tokens"] / 1e6 * p_out})
        return sorted(out, key=lambda r: -r["cost_usd"])

    @property
    def cost(self) -> float:
        return sum(r["cost_usd"] for r in self.rows())


# --------------------------------------------------------------------------- clients

class ClaudeClient:
    """Structured-output calls to Claude that record token usage."""

    def __init__(self, usage: Usage, models: tuple[str, ...]):
        from langchain_anthropic import ChatAnthropic
        self.usage = usage
        self.llm = {m: ChatAnthropic(model=m, max_tokens=2048, max_retries=3) for m in models}

    def structured(self, model: str, schema, messages):
        out = self.llm[model].with_structured_output(schema, method="json_schema", include_raw=True).invoke(messages)
        um = getattr(out["raw"], "usage_metadata", None) or {}
        self.usage.add(model, um.get("input_tokens", 0), um.get("output_tokens", 0))
        if out.get("parsing_error"):
            raise out["parsing_error"]
        return out["parsed"]


class JevClient:
    """TypeSafe's Jev decision model: typed questions in, probabilities out."""

    def __init__(self, usage: Usage, model: str, client=None):
        if client is None:
            from typesafe_sdk import TypeSafeClient
            client = TypeSafeClient(model=model)       # reads TYPESAFE_API_KEY; retries 429s and timeouts
        self.client, self.model, self.usage = client, model, usage

    def ask(self, state, questions: dict) -> dict:
        r = self.client.system_one(state=state, questions=questions, model=self.model)
        self.usage.add("jev", r.usage.input_tokens, r.usage.output_tokens)
        return r.answers


# --------------------------------------------------------------------------- prompts

COMMON_RULES = """You work for Acme SaaS (the vendor) and answer questions from a prospect's
due-diligence questionnaire using ONLY Acme's internal policy pack.
Rules:
- Every statement must come from a retrieved policy section. Never use outside knowledge about
  Acme or assume typical industry practice.
- If the sections do not answer the question, say so. Do not guess or fill gaps.
- Do not add guarantees, promises or commitments that the policy does not state."""

SPECIALIST_FOCUS = {
    "security": "You are Acme's security specialist. Be precise about certifications, scopes, "
                "time frames and technical controls.",
    "ai_governance": "You are Acme's AI governance specialist. Be precise about how customer data "
                     "is (and is not) used by AI, model providers, human oversight and regulatory "
                     "positioning. Never overstate certifications that are only in progress.",
    "privacy": "You are Acme's privacy specialist. Be precise about controller/processor roles, "
               "retention periods, deletion, sub-processors and data locations.",
}

DRAFT_PROMPT = """Write the questionnaire answer from the passages provided.
- Answer exactly what was asked, in 1 to 3 sentences of plain professional English, in Acme's voice ("Acme ...", "We ...").
- Include the specifics the question asks for (numbers, time frames, standards). Do not add related
  facts the question didn't ask about: every extra sentence is one more claim a reviewer must check.
- For a yes/no question, start with "Yes." or "No." only when a passage states it directly.
- Do not put section IDs in the answer text; list them in cited_section_ids.
- Refer to the prospect as "the customer" (or "customers"), never by their company name, so the answer
  can be reused for other prospects.
- Put anything meant for the internal reviewer (gaps, caveats, "the policy does not say...") in
  reviewer_note, never in the answer. Leave reviewer_note empty unless there is something the reviewer
  should act on; don't list details the policy omits if they don't change this answer.
- If the passages do not answer the question, set covered=false, answer="" and cited_section_ids=[]."""

EXTRACT_PROMPT = """Split the questionnaire answer into its individual factual claims. A bare "Yes." or
"No." is not a separate claim: treat it as part of the claim that follows. For each claim, pick the one
cited section that supports it and copy the exact supporting words from that section into evidence_quote:
verbatim, no paraphrasing, no ellipses. If no cited section supports a claim, leave both fields empty."""

JUDGE_PROMPT = """You are an independent auditor. Decide whether every statement in the vendor's answer
is supported by the cited policy sections. Wording may differ; meaning may not. List any statement the
sections do not support. Ignore statements that only restate the question."""

# --------------------------------------------------------------------------- rule-based checks

RESTRICTED_RULES = {
    "guarantee": r"\bguarantee",
    "warranty": r"\bwarrant",
    "liability": r"\bliabilit|\bliable\b",
    "indemnity": r"\bindemn",
    "commitment": r"\bcommit(ment)? to\b|\bcontractual|\bin (the|our|your) contract\b",
    "sla / credits": r"\bSLA\b|service credit|\bpenalt",
    "confidential report": r"\b(full|complete) (pen(etration)? test|audit|soc ?2) report",
}


def keyword_flags(question: str) -> list[str]:
    return [f"keyword rule: {name}" for name, rx in RESTRICTED_RULES.items() if re.search(rx, question, re.I)]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%.]", " ", s.lower())).strip()


NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers_match(claim: str, section_text: str) -> bool:
    """Every number in the claim must appear in the cited section (Jev is weak at numbers)."""
    have = set(NUM.findall(section_text))
    return all(n in have for n in NUM.findall(claim))


# --------------------------------------------------------------------------- Jev questions

def jev_questions():
    """Built lazily so the package imports without typesafe_sdk installed (e.g. demo mode)."""
    from typesafe_sdk import Choice, Noul
    return {
        "classify": {
            "category": Choice(
                instructions="Which specialist at a SaaS vendor should answer this due-diligence question?",
                criteria={
                    "security": "Information security programme, certifications, access control, encryption, "
                                "vulnerabilities, hosting, network, identity/SSO, incident response, continuity.",
                    "ai_governance": "AI features, models and model providers, training on data, AI risk "
                                     "management, AI regulation (EU AI Act, NIST AI RMF, ISO 42001), AI testing.",
                    "privacy": "Personal data, GDPR, data processing agreements, retention and deletion, "
                               "sub-processors, data transfers, data subject rights."}),
            "asks_guarantee": Noul(instructions="The question asks the vendor to guarantee or warrant an outcome."),
            "asks_contract_terms": Noul(instructions=(
                "The question asks the vendor to agree new contractual terms, an SLA, penalties or service "
                "credits, rather than to describe its existing policy or practice.")),
            "asks_liability": Noul(instructions="The question asks the vendor to accept liability or to indemnify the customer."),
            "asks_confidential_document": Noul(instructions=(
                "The question asks the vendor to hand over a complete confidential document, such as a full "
                "audit report or penetration test report.")),
        },
        "gate": {
            "is_relevant": Noul(instructions="The passage addresses the subject of the question."),
            "has_evidence": Noul(instructions=(
                "The passage states information that directly answers the question, or at least one part of it.")),
        },
        "complete": {"answers_every_part": Noul(instructions=(
            "Taken together, the passages contain the information needed to answer every part of the question."))},
        "relation": {"relation": Choice(
            instructions="How does the section relate to the claim?",
            criteria={"supports": "The section states the claim or directly implies that it is true.",
                      "contradicts": "The section states the opposite of the claim or implies that it is false.",
                      "says_nothing": "The section does not address the claim either way."})},
        "note": {"needs_check": Noul(instructions=(
            "The note says something must be checked, confirmed or changed before the answer is sent to the customer."))},
        "same": {"same": Noul(instructions=(
            "Both questions ask for the same information, so an answer to the approved question would fully "
            "answer the new question."))},
    }


COMMIT_KEYS = ["asks_guarantee", "asks_contract_terms", "asks_liability", "asks_confidential_document"]

CHOICE_CRITERIA = {
    "yes": "The answer confirms what the question asks about.",
    "no": "The answer denies what the question asks about.",
    "partial": "The answer confirms part of what the question asks about, or only with conditions.",
    "n/a": "The question does not apply to the vendor or its service.",
}
