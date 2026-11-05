"""The LangGraph pipelines.

Per question:  Jev classify -> library lookup --hit--> reuse approved answer
                                      \\--miss--> search + Jev gate -> Claude draft -> claim checks -> note check -> score
Per questionnaire:  Send fan-out (answer every question) -> review (interrupt per question) -> finalise
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from .agents import (CHOICE_CRITERIA, COMMIT_KEYS, COMMON_RULES, DRAFT_PROMPT, EXTRACT_PROMPT, SPECIALIST_FOCUS,
                     ClaudeClient, JevClient, Usage, jev_questions, keyword_flags, norm, numbers_match)
from .config import ESCALATE_TEXT, Settings
from .library import AnswerLibrary
from .retrieval import PolicyIndex, format_hits
from .state import ClaimList, DraftAnswer, QState, RunState

ICONS = {"auto_approve": "🟢", "human_review": "🟡", "escalate": "🔴", "error": "⚠️"}
REVIEW_PRIORITY = {"restricted": 0, "escalate": 1, "error": 2, "Low": 3, "Medium": 4}


class Responder:
    """Answers questionnaire questions from a policy pack. Inject `claude`/`jev` to test without API calls."""

    def __init__(self, index: PolicyIndex, settings: Settings | None = None, library: AnswerLibrary | None = None,
                 claude: ClaudeClient | None = None, jev: JevClient | None = None, usage: Usage | None = None):
        self.s = settings or Settings()
        self.index, self.library = index, library
        self.usage = usage or Usage()
        self.claude = claude or ClaudeClient(self.usage, (self.s.draft_model, self.s.extract_model))
        self.jev = jev or JevClient(self.usage, self.s.jev_model)
        self.q = jev_questions()
        self.pool = ThreadPoolExecutor(max_workers=self.s.jev_workers)
        self.graph = self._build_question_graph()

    # ------------------------------------------------------------------ nodes
    def classify(self, state: QState) -> dict:
        q = state["question"]
        a = self.jev.ask({"questionnaire_question": q}, self.q["classify"])
        p = {k: round(a[k].noul, 3) for k in COMMIT_KEYS}
        reasons = keyword_flags(q) + [f"Jev: {k} p={v:.2f}" for k, v in p.items() if v >= self.s.yes]
        caps = [f"Jev unsure whether it {k.replace('_', ' ')} (p={v:.2f})"
                for k, v in p.items() if self.s.no <= v < self.s.yes]
        cat = a["category"]
        return {"classification": {"category": cat.choice, "confidence": round(cat.confidence, 3)},
                "restricted": bool(reasons), "restricted_reasons": reasons, "caps": caps,
                "jev": {"category_conf": round(cat.confidence, 3), **{f"p_{k}": v for k, v in p.items()}}}

    def library_lookup(self, state: QState) -> dict:
        if self.library is None or len(self.library) == 0:
            return {"library": None}
        same = lambda new, old: self.jev.ask({"new_question": new, "approved_question": old}, self.q["same"])["same"].noul
        return {"library": self.library.lookup(state["question"], self.index.versions, same, self.s.library_match)}

    def library_answer(self, state: QState) -> dict:
        m = state["library"]["match"]
        reason = (f"reused approved answer #{m['id']} ({m['decision']} by {m['reviewer']} on {m['approved_at'][:10]}; "
                  f"Jev same-question p={m['p_same']:.2f})")
        if state["restricted"]:
            level, status = "Medium", "human_review"
            reasons = [reason, *[f"restricted topic, {r}" for r in state["restricted_reasons"]],
                       "commitments are always re-checked by a human"]
        else:
            level, status, reasons = "High", "auto_approve", [reason]
        return {"result": {"question": state["question"], "category": state["classification"]["category"],
                           "answer": m["answer"], "draft_answer": m["answer"], "sources": json.loads(m["sources"]),
                           "confidence": level, "status": status, "reasons": reasons, "reviewer_note": "",
                           "signals": {"library_match": True, "library_id": m["id"], "p_same": m["p_same"],
                                       "restricted": state["restricted"], **state.get("jev", {})}},
                "passages": {}, "grounding": {"claims": []}, "search_log": ["(library hit)"]}

    def gate(self, state: QState) -> dict:
        q = state["question"]
        hits = self.index.search(q, k=self.s.search_k)

        def judge(h):
            a = self.jev.ask({"question": q, "passage": {"id": h["section_id"], "title": h["heading"], "text": h["text"]}},
                             self.q["gate"])
            return h, a["is_relevant"].noul, a["has_evidence"].noul

        judged = list(self.pool.map(judge, hits))
        kept = {h["section_id"]: {**h, "p_relevant": round(r, 3), "p_evidence": round(e, 3)}
                for h, r, e in judged if r >= self.s.gate_relevant and e >= self.s.gate_evidence}
        jev = {**state.get("jev", {}), "gate": {h["section_id"]: [round(r, 2), round(e, 2)] for h, r, e in judged},
               "sections_kept": len(kept)}
        caps = list(state.get("caps", []))
        if kept:
            a = self.jev.ask({"question": q, "passages": [{"id": s, "text": h["text"]} for s, h in kept.items()]},
                             self.q["complete"])
            jev["p_complete"] = round(a["answers_every_part"].noul, 3)
            if jev["p_complete"] < self.s.complete:
                caps.append(f"sections may not answer every part of the question (p={jev['p_complete']:.2f})")
        return {"passages": kept, "jev": jev, "caps": caps,
                "search_log": [f"{len(hits)} sections found, {len(kept)} passed the Jev gate"]}

    def draft(self, state: QState) -> dict:
        if not state["passages"]:
            return {"draft": {"covered": False, "answer": "", "cited_section_ids": [], "reviewer_note": ""}}
        category = state["classification"]["category"]
        ranked = sorted(state["passages"].values(), key=lambda h: -h["score"])
        d = self.claude.structured(self.s.draft_model, DraftAnswer, [
            SystemMessage(COMMON_RULES + "\n\n" + SPECIALIST_FOCUS[category] + "\n\n" + DRAFT_PROMPT),
            HumanMessage(f"Question: {state['question']}\n\nPolicy sections:\n\n{format_hits(ranked)}")]).model_dump()
        d["cited_section_ids"] = [s for s in dict.fromkeys(d["cited_section_ids"]) if s in state["passages"]]
        return {"draft": d}

    def verify(self, state: QState) -> dict:
        d = state["draft"]
        if not d["covered"] or not d["cited_section_ids"]:
            return {"grounding": {"claims": []}}
        cited = {s: state["passages"][s] for s in d["cited_section_ids"]}
        extracted = self.claude.structured(self.s.extract_model, ClaimList, [
            SystemMessage(EXTRACT_PROMPT),
            HumanMessage(f"Answer: {d['answer']}\n\nCited sections:\n\n{format_hits(list(cited.values()))}")])

        def check(c):
            c = c.model_dump()                                     # one copy, then read and write that copy
            section = cited.get(c["cited_section_id"])
            if section is None and len(cited) == 1:                # the extractor left the source blank
                c["cited_section_id"], section = next(iter(cited.items()))
            quote = c["evidence_quote"].strip()
            c["quote_found"] = bool(section and quote and norm(quote) in norm(section["text"]))
            c["numbers_ok"] = bool(section) and numbers_match(c["claim"], section["text"])
            if section is None:
                c["verdict"], c["note"] = "unsupported", "cited a section that wasn't retrieved"
                return c
            if quote and not c["quote_found"]:
                c["verdict"], c["note"] = "unsupported", "quote not found in the section"
                return c
            rel = self.jev.ask({"claim": c["claim"], "section": section["text"]}, self.q["relation"])["relation"]
            c["jev_relation"], c["jev_confidence"] = rel.choice, round(rel.confidence, 3)
            if rel.choice == "contradicts":
                c["verdict"], c["contradicted"], c["note"] = "unsupported", True, f"Jev: contradicts ({rel.confidence:.2f})"
            elif rel.choice == "says_nothing":
                c["verdict"], c["note"] = "unsupported", f"Jev: section says nothing about it ({rel.confidence:.2f})"
            elif not c["numbers_ok"]:
                c["verdict"], c["note"] = "unsupported", "a number in the claim isn't in the section"
            elif not quote:
                c["verdict"], c["note"] = "inferred", "no quote given; Jev judged the whole section"
            elif rel.confidence >= self.s.support_conf:
                c["verdict"] = "explicit"
            else:
                c["verdict"], c["note"] = "inferred", f"Jev: supports, low confidence ({rel.confidence:.2f})"
            return c

        return {"grounding": {"claims": list(self.pool.map(check, extracted.claims))}}

    def note_check(self, state: QState) -> dict:
        d = state["draft"]
        note = (d.get("reviewer_note") or "").strip()
        if not d["covered"] or not note:
            return {}
        p = self.jev.ask({"reviewer_note": note}, self.q["note"])["needs_check"].noul
        caps = list(state.get("caps", []))
        if p >= self.s.note_hold:
            caps.append(f"reviewer note asks for a check before sending (p={p:.2f})")
        return {"jev": {**state.get("jev", {}), "p_note_needs_check": round(p, 3)}, "caps": caps}

    def score(self, state: QState) -> dict:
        s, d, claims = self.s, state["draft"], state["grounding"]["claims"]
        n = len(claims)
        support = sum(c["verdict"] != "unsupported" for c in claims) / n if n else 0.0
        explicit = sum(c["verdict"] == "explicit" for c in claims) / n if n else 0.0
        caps = state.get("caps", [])
        signals = {"library_match": False, "claims": n, "claim_support": round(support, 2),
                   "explicit_evidence": round(explicit, 2), "restricted": state["restricted"], **state.get("jev", {})}
        reasons, answer = [], d["answer"]
        if not d["covered"] or n == 0 or support == 0:
            level, answer = "Low", ESCALATE_TEXT
            reasons.append("policy pack doesn't cover this question")
        elif support >= s.high_min_support and explicit >= s.high_min_explicit and not caps:
            level = "High"
            reasons.append("every claim is backed by a verified quote from a cited section")
        elif support >= s.medium_min_support:
            level = "Medium"
            if explicit < s.high_min_explicit:
                reasons.append("some claims are inferred rather than stated")
            if support < 1:
                reasons.append("some claims are unsupported")
            reasons += caps
        else:
            level = "Low"
            reasons.append(f"only {support:.0%} of claims are supported")
        if any(c.get("contradicted") for c in claims):
            level = "Low"
            reasons.append("a claim contradicts the cited policy")
        if state["restricted"]:
            level = "Low"
            reasons += [f"restricted topic, {r}" for r in state["restricted_reasons"]]
        status = ("escalate" if answer == ESCALATE_TEXT
                  else "auto_approve" if level in s.auto_approve_levels else "human_review")
        return {"result": {"question": state["question"], "category": state["classification"]["category"],
                           "answer": answer, "draft_answer": d["answer"],
                           "sources": d["cited_section_ids"] if answer != ESCALATE_TEXT else [],
                           "confidence": level, "status": status, "reasons": reasons, "signals": signals,
                           "reviewer_note": d.get("reviewer_note", "")}}

    # ------------------------------------------------------------------ graphs
    def _build_question_graph(self):
        b = StateGraph(QState)
        for name, fn in [("jev_classify", self.classify), ("library_lookup", self.library_lookup),
                         ("library_answer", self.library_answer), ("search_and_jev_gate", self.gate),
                         ("draft", self.draft), ("verify", self.verify), ("note_check", self.note_check),
                         ("score", self.score)]:
            b.add_node(name, fn)
        b.add_edge(START, "jev_classify")
        b.add_edge("jev_classify", "library_lookup")
        b.add_conditional_edges(
            "library_lookup",
            lambda st: "library_answer" if st.get("library") and st["library"]["match"] else "search_and_jev_gate",
            ["library_answer", "search_and_jev_gate"])
        b.add_edge("library_answer", END)
        for a, z in [("search_and_jev_gate", "draft"), ("draft", "verify"), ("verify", "note_check"),
                     ("note_check", "score"), ("score", END)]:
            b.add_edge(a, z)
        return b.compile()

    def answer(self, question: str) -> dict:
        """Answer one question. Returns the result plus claims, search log and source titles."""
        st = self.graph.invoke({"question": question})
        r = {**st["result"], "claims": st["grounding"]["claims"], "search_log": st["search_log"]}
        r["source_titles"] = [f"{self.index.titles.get(s, '?')} §{s}" for s in r["sources"]]
        return r

    def choose_response(self, question: str, answer: str, options: list[str]) -> dict:
        """Pick the value for a Yes/No/Partial/N/A dropdown with a Jev Choice question."""
        from typesafe_sdk import Choice
        criteria = {o: CHOICE_CRITERIA.get(o.strip().lower()) for o in options}
        q = {"response": Choice(instructions="Which dropdown response best matches the vendor's answer to the question?",
                                criteria=criteria)}
        a = self.jev.ask({"question": question, "vendor_answer": answer}, q)["response"]
        return {"choice": a.choice, "confidence": round(a.confidence, 3)}

    def build_run_graph(self, checkpointer, reviewer: str = "", run_id: str = ""):
        """Questionnaire graph: answer all (Send) -> review (interrupt per item) -> finalise. Needs a checkpointer."""

        def fan_out(state: RunState):
            return [Send("answer_one", item) for item in state["items"]]

        def answer_one(item: dict) -> dict:
            t0 = time.time()
            try:
                r = self.answer(item["model_question"])
            except Exception as e:                                  # one failure must not stop the run
                r = {"question": item["model_question"], "answer": "", "draft_answer": "", "sources": [],
                     "source_titles": [], "category": "", "confidence": "Low", "status": "error",
                     "reasons": [f"{type(e).__name__}: {e}"], "reviewer_note": "", "signals": {}, "claims": [],
                     "search_log": []}
            r["seconds"] = round(time.time() - t0, 1)
            return {"results": [{**r, **item}]}

        def review(state: RunState) -> dict:
            # Re-runs from the top on every resume; LangGraph replays earlier decisions in order.
            # So this node only collects decisions; every write happens in finalise.
            queue, decisions = review_queue(state["results"]), []
            for n, r in enumerate(queue, start=1):
                payload = {"n": n, "total": len(queue), "ref": r["ref"], "sheet": r["sheet"], "question": r["question"],
                           "status": r["status"], "confidence": r["confidence"], "draft": r["draft_answer"],
                           "reviewer_note": r.get("reviewer_note", ""), "sources": r["source_titles"],
                           "reasons": r["reasons"],
                           "claims": [f"{c['verdict']}: {c['claim']}" + (f" ({c['note']})" if c.get("note") else "")
                                      for c in r.get("claims", [])]}
                decisions.append({"key": [r["sheet"], r["row"]], **interrupt(payload)})
            return {"decisions": decisions}

        def finalise(state: RunState) -> dict:
            by_key = {tuple(d["key"]): d for d in state["decisions"]}
            final, added, reused = [], 0, 0
            for r in state["results"]:
                d = by_key.get((r["sheet"], r["row"]))
                from_library = bool(r["signals"].get("library_match"))
                if d is None:
                    f = {**r, "final_answer": r["answer"], "decision": "auto_approved", "reviewer": "", "decided_at": ""}
                    if self.library is not None and self.s.add_auto_to_library and not from_library:
                        self.library.add(r["model_question"], r["answer"], r["sources"], r["category"],
                                         "auto_approved", "pipeline (High)", self.index.versions, run_id)
                        added += 1
                elif d["action"] in ("approve", "edit"):
                    text = r["draft_answer"] if d["action"] == "approve" else d["answer"]
                    f = {**r, "final_answer": text, "decision": "approved" if d["action"] == "approve" else "edited",
                         "reviewer": d.get("reviewer", reviewer), "decided_at": d.get("at", ""),
                         "review_comment": d.get("comment", "")}
                    if self.library is not None and not from_library:
                        self.library.add(r["model_question"], text, r["sources"], r["category"], f["decision"],
                                         f["reviewer"], self.index.versions, run_id)
                        added += 1
                else:
                    f = {**r, "final_answer": "", "decision": "rejected", "reviewer": d.get("reviewer", reviewer),
                         "decided_at": d.get("at", ""), "review_comment": d.get("comment", "")}
                if from_library and self.library is not None:
                    self.library.bump(r["signals"]["library_id"])
                    reused += 1
                if f["final_answer"] and r.get("choice_col") is not None:          # fill Yes/No dropdowns
                    try:
                        f["response_choice"] = self.choose_response(r["question"], f["final_answer"], r["choice_options"])
                    except Exception as e:
                        f["response_choice"] = {"choice": "", "error": str(e)}
                final.append(f)
            return {"final": final, "summary": {"added_to_library": added, "library_reuses": reused,
                                                "finished_at": datetime.now().isoformat(timespec="seconds")}}

        rb = StateGraph(RunState)
        rb.add_node("answer_one", answer_one)
        rb.add_node("review", review)
        rb.add_node("finalise", finalise)
        rb.add_conditional_edges(START, fan_out, ["answer_one"])
        rb.add_edge("answer_one", "review")
        rb.add_edge("review", "finalise")
        rb.add_edge("finalise", END)
        return rb.compile(checkpointer=checkpointer)


def review_queue(results: list[dict]) -> list[dict]:
    """Everything not auto-approved, most important first: restricted, escalated, errors, Low, Medium."""
    todo = [r for r in results if r["status"] != "auto_approve"]
    key = lambda r: (REVIEW_PRIORITY["restricted"] if r["signals"].get("restricted") else
                     REVIEW_PRIORITY.get(r["status"], REVIEW_PRIORITY.get(r["confidence"], 5)), r["sheet"], r["row"])
    return sorted(todo, key=key)


def decision(action: str, reviewer: str, answer: str = "", comment: str = "") -> dict:
    """Payload to resume the review graph with: Command(resume=decision(...))."""
    assert action in ("approve", "edit", "reject")
    return {"action": action, "answer": answer, "comment": comment, "reviewer": reviewer,
            "at": datetime.now().isoformat(timespec="seconds")}
