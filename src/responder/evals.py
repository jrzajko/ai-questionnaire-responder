"""Score the pipeline against an answer key: safety, usefulness, routing, citations and faithfulness."""
from __future__ import annotations

import csv
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import HumanMessage, SystemMessage

from .agents import JUDGE_PROMPT
from .config import OPUS
from .io import extract_questions
from .state import JudgeVerdict

# What each kind of question in the answer key should lead to.
EXPECT = {"high": {"auto_approve"}, "medium": {"human_review"}, "gap": {"escalate"},
          "partial": {"human_review", "escalate"}, "restricted": {"human_review", "escalate"}}


def load_eval_set(key_csv, questionnaire=None) -> list[dict]:
    """Rows of the answer key. With a questionnaire, questions are taken from it (sub-questions get context)."""
    key = list(csv.DictReader(open(key_csv, encoding="utf-8")))
    if questionnaire is None:
        return [{**k, "model_question": k["question"]} for k in key]
    items = {(i["sheet"], i["ref"]): i for i in extract_questions(questionnaire)[0]}
    return [{**k, "model_question": items[(k["sheet"], k["ref"])]["model_question"]}
            for k in key if (k["sheet"], k["ref"]) in items]


def judge(responder, result, model=OPUS) -> dict:
    """LLM judge (a different model from the drafter): is every statement supported by the cited sections?"""
    sections = "\n\n".join(f"[{s}] {responder.index.by_id[s]['text']}" for s in result["sources"] if s in responder.index.by_id)
    v = responder.claude.structured(model, JudgeVerdict, [
        SystemMessage(JUDGE_PROMPT),
        HumanMessage(f"Question: {result['question']}\n\nAnswer: {result['answer']}\n\nCited sections:\n\n{sections}")])
    return v.model_dump()


def run_eval(responder, rows: list[dict], judge_model: str | None = OPUS, max_parallel: int = 6):
    """Answer every row (no library, no review) and score it. Returns (per-question rows, metrics)."""
    llm = getattr(responder.claude, "llm", None)
    if judge_model and llm is not None and judge_model not in llm:
        from langchain_anthropic import ChatAnthropic
        llm[judge_model] = ChatAnthropic(model=judge_model, max_tokens=1024, max_retries=3)
    responder.usage.reset()
    t0 = time.time()

    def one(row):
        try:
            r = responder.answer(row["model_question"])
        except Exception as e:
            return {**row, "status": "error", "confidence": "", "answer": "", "sources": [], "category": "",
                    "reasons": [f"{type(e).__name__}: {e}"], "faithful": None}
        out = {**row, **{k: r[k] for k in ("status", "confidence", "answer", "sources", "category", "reasons")},
               "faithful": None, "unsupported": []}
        if judge_model and r["status"] != "escalate" and r["sources"]:
            v = judge(responder, r, judge_model)
            out["faithful"], out["unsupported"] = v["faithful"], v["unsupported"]
        return out

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        results = list(pool.map(one, rows))
    return results, metrics(results, responder.usage.cost, round(time.time() - t0))


def metrics(results: list[dict], cost: float = 0.0, seconds: int = 0) -> dict:
    n = len(results)
    by = lambda outcome: [r for r in results if r["expected_outcome"] == outcome]
    auto = [r for r in results if r["status"] == "auto_approve"]
    sourced = [r for r in results if r["expected_sources"] and r["status"] != "escalate"]
    judged = [r for r in results if r.get("faithful") is not None]
    pct = lambda a, b: round(a / b, 3) if b else None
    return {
        "questions": n,
        "outcome_correct": pct(sum(r["status"] in EXPECT[r["expected_outcome"]] for r in results), n),
        "unsafe_auto_approvals": sum(r["expected_outcome"] != "high" for r in auto),
        "answerable_auto_approved": f"{sum(r['status'] == 'auto_approve' for r in by('high'))}/{len(by('high'))}",
        "precision_of_high": pct(sum(r["expected_outcome"] == "high" for r in auto), len(auto)),
        "traps_escalated": f"{sum(r['status'] == 'escalate' for r in by('gap'))}/{len(by('gap'))}",
        "answerable_wrongly_escalated": sum(r["status"] == "escalate" for r in by("high")),
        "restricted_held": f"{sum(r['status'] != 'auto_approve' for r in by('restricted'))}/{len(by('restricted'))}",
        "routing_correct": pct(sum(r["category"] in r["expected_category"].split("|") for r in results), n),
        "citation_coverage": pct(sum(bool(set(r["expected_sources"].split(";")) & set(r["sources"])) for r in sourced),
                                 len(sourced)),
        "faithfulness": pct(sum(r["faithful"] for r in judged), len(judged)),
        "errors": sum(r["status"] == "error" for r in results),
        "cost_usd": round(cost, 4),
        "seconds": seconds,
    }


def scorecard_markdown(name: str, m: dict) -> str:
    labels = {
        "outcome_correct": "Correct outcome", "unsafe_auto_approvals": "**Unsafe auto-approvals**",
        "answerable_auto_approved": "Answerable questions auto-approved", "precision_of_high": "Precision of High",
        "traps_escalated": "Traps escalated", "answerable_wrongly_escalated": "Answerable questions wrongly escalated",
        "restricted_held": "Restricted questions held back", "routing_correct": "Routed to the right specialist",
        "citation_coverage": "Cites the expected section", "faithfulness": "Faithful (LLM judge)",
        "errors": "Errors", "cost_usd": "Cost (USD)", "seconds": "Time (s)"}
    fmt = lambda v: f"{v:.0%}" if isinstance(v, float) and v <= 1 and not isinstance(v, bool) else str(v)
    rows = "\n".join(f"| {labels[k]} | {fmt(m[k]) if k != 'cost_usd' else f'${m[k]:.3f}'} |" for k in labels if k in m)
    return f"### {name} ({m['questions']} questions)\n\n| Metric | Result |\n|---|---|\n{rows}\n"


def write_outputs(results, m, out_dir, name):
    import json
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"eval_{name}.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["sheet", "ref", "question", "expected_outcome", "status", "confidence", "expected_category", "category",
                "expected_sources", "sources", "faithful", "unsupported", "answer", "reasons"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow({**r, "sources": ";".join(r["sources"]), "reasons": " | ".join(r["reasons"]),
                        "unsupported": " | ".join(r.get("unsupported") or [])})
    (out_dir / f"eval_{name}.json").write_text(json.dumps(m, indent=2))
    (out_dir / f"eval_{name}.md").write_text(scorecard_markdown(name, m))
    return out_dir / f"eval_{name}.md"
