"""Offline stand-ins for Claude and Jev, so the whole pipeline runs in tests with no API keys or cost.

The fakes return the same types as the real clients (Pydantic models; typesafe_sdk response objects),
so the code paths are the real ones; only the model judgements are scripted."""
import json
import pathlib
import re

import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, SystemOneResponse, Usage as TSUsage

from responder.agents import JevClient, Usage
from responder.config import Settings
from responder.graph import Responder
from responder.retrieval import PolicyIndex
from responder.state import ClaimList, DraftAnswer, JudgeVerdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
STOP = {"the", "and", "you", "your", "for", "are", "with", "what", "how", "our", "any", "does", "have", "this",
        "that", "from", "within", "which", "acme", "data", "customer", "customers", "question", "passage"}


def words(text):
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP}


class FakeTypeSafe:
    """Scripted Jev: overlap-based relevance, regex commitment checks, 'confirm' notes need a check."""

    def __init__(self):
        self.calls = []

    def system_one(self, state, questions, model=None):
        self.calls.append(sorted(questions))
        text = json.dumps(state).lower()
        answers = {}
        for key, q in questions.items():
            if q.type == "choice":
                opts = list(q.criteria)
                if "supports" in opts:
                    pick = "supports"
                elif "security" in opts:
                    qtxt = state["questionnaire_question"].lower()
                    pick = ("ai_governance" if re.search(r"\bai\b|model", qtxt) else
                            "privacy" if re.search(r"personal|sub-processor|delet|retention|gdpr", qtxt) else "security")
                else:                                              # dropdown response
                    ans = state["vendor_answer"].lower()
                    want = "yes" if ans.startswith("yes") else "no" if ans.startswith("no") else "partial"
                    pick = next((o for o in opts if o.lower() == want), opts[0])
                probs = {o: (0.94 if o == pick else 0.06 / max(len(opts) - 1, 1)) for o in opts}
                answers[key] = ChoiceAnswer(choice=pick, confidence=0.9, probabilities=probs)
                continue
            if key.startswith("asks_"):
                p = 0.93 if re.search(r"guarantee|contractually|indemn|unlimited liab|service credit", text) else 0.05
            elif key in ("is_relevant", "has_evidence"):
                overlap = words(state["question"]) & words(state["passage"]["text"] + " " + state["passage"]["title"])
                p = 0.92 if len(overlap) >= 2 else 0.1
            elif key == "answers_every_part":
                p = 0.9
            elif key == "needs_check":
                p = 0.9 if "confirm" in text else 0.1
            elif key == "same":
                p = 0.97 if state["new_question"] == state["approved_question"] else 0.08
            else:
                p = 0.5
            answers[key] = NoulAnswer(noul=p)
        return SystemOneResponse(model="jev-1.13.0", usage=TSUsage(input_tokens=200, output_tokens=5), answers=answers)


def first_sentence(text):
    return text.split(". ")[0].rstrip(".") + "."


class FakeClaude:
    """Scripted Claude: drafts the first sentence of the top section; quotes it verbatim as the claim."""

    def __init__(self, usage, note=""):
        self.usage, self.calls, self.note = usage, [], note

    def structured(self, model, schema, messages):
        self.calls.append(schema.__name__)
        self.usage.add(model, 900, 80)
        sections = re.findall(r"\[([A-Z]+-\d+)\][^\n]*\(score [\d.]+\)\n([^\n]+)", messages[-1].content)
        if schema is DraftAnswer:
            assert "never by their company name" in messages[0].content
            if not sections:
                return DraftAnswer(covered=False, answer="", cited_section_ids=[], reviewer_note="")
            sid, text = sections[0]
            return DraftAnswer(covered=True, answer=first_sentence(text), cited_section_ids=[sid],
                               reviewer_note=self.note(sid) if callable(self.note) else self.note)
        if schema is ClaimList:
            sid, text = sections[0]
            return ClaimList(claims=[{"claim": first_sentence(text), "cited_section_id": sid,
                                      "evidence_quote": first_sentence(text).rstrip(".")}])
        if schema is JudgeVerdict:
            return JudgeVerdict(faithful=True, unsupported=[])
        raise AssertionError(schema)


@pytest.fixture(scope="session")
def index():
    return PolicyIndex(ROOT / "data" / "policies")


@pytest.fixture
def make_responder(index):
    def make(library=None, note="", settings=None):
        usage = Usage()
        jev_fake = FakeTypeSafe()
        r = Responder(index, settings or Settings(), library=library, usage=usage,
                      claude=FakeClaude(usage, note), jev=JevClient(usage, "jev-latest", client=jev_fake))
        r.jev_fake = jev_fake
        return r
    return make
