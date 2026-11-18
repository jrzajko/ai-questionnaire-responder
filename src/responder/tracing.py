"""Optional LangSmith observability.

Nothing here does anything unless tracing is switched on with environment variables:
    LANGSMITH_TRACING=true  LANGSMITH_API_KEY=...  LANGSMITH_PROJECT=ai-questionnaire-responder
(and LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com for an EU-region account).

When it is on:
- LangGraph nodes and Claude calls are traced automatically by LangChain;
- Jev calls, which go through TypeSafe's own SDK, are traced by the `traced_jev_ask` wrapper below;
- each question's trace is tagged with its sheet and ref, so it can be found in the LangSmith UI;
- reviewer decisions are attached to that question's trace as feedback (approve 1, edit 0.5, reject 0).

Privacy: traces hold prompts and answers. Set LANGSMITH_HIDE_INPUTS=true / LANGSMITH_HIDE_OUTPUTS=true
to keep content out of LangSmith while still recording structure, timings and token counts.
"""
from __future__ import annotations

import os

from langsmith import traceable                         # installed with langchain-core
from langsmith.run_helpers import get_current_run_tree
from langsmith.utils import ContextThreadPoolExecutor, tracing_is_enabled

__all__ = ["ContextThreadPoolExecutor", "enabled", "traceable", "current_run_ids", "jev_inputs", "jev_outputs",
           "log_decision", "DECISION_SCORE"]

DECISION_SCORE = {"approve": 1.0, "edit": 0.5, "reject": 0.0}
_client = None


def enabled() -> bool:
    """True only when tracing is switched on and a key is present."""
    return bool(tracing_is_enabled()) and bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"))


def current_run_ids() -> dict:
    """IDs of the run being traced right now (empty when tracing is off)."""
    if not enabled():
        return {}
    rt = get_current_run_tree()
    return {"trace_run_id": str(rt.id), "trace_id": str(rt.trace_id)} if rt else {}


# ------------------------------------------------------------------ Jev: make the typed calls readable in a trace
def _text(x) -> str:
    return x if isinstance(x, str) else str(x)


def jev_inputs(inputs: dict) -> dict:
    """Show the state Jev saw and each question's type and wording (not the SDK objects)."""
    qs = {}
    for key, q in (inputs.get("questions") or {}).items():
        d = {"type": getattr(q, "type", "?"), "instructions": _text(getattr(q, "instructions", "") or "")}
        crit = getattr(q, "criteria", None)
        if isinstance(crit, dict):
            d["options"] = list(crit)
        qs[key] = d
    return {"state": inputs.get("state"), "questions": qs}


def jev_outputs(answers) -> dict:
    """Turn Jev's answer objects into plain probabilities."""
    out = {}
    for key, a in (answers or {}).items():
        if hasattr(a, "choice"):
            out[key] = {"choice": a.choice, "confidence": round(a.confidence, 3),
                        "probabilities": {k: round(v, 3) for k, v in (a.probabilities or {}).items()}}
        elif hasattr(a, "noul"):
            out[key] = {"p_yes": round(a.noul, 3)}
        else:
            out[key] = _text(a)
    return out


# ------------------------------------------------------------------ reviewer decisions -> feedback
def log_decision(result: dict, decision: dict) -> bool:
    """Attach a reviewer's approve / edit / reject to the question's trace. Never raises."""
    run_id = result.get("trace_run_id")
    if not (run_id and enabled()):
        return False
    global _client
    try:
        if _client is None:
            from langsmith import Client
            _client = Client()
        action = decision.get("action", "")
        _client.create_feedback(
            run_id, key="reviewer_decision", trace_id=result.get("trace_id") or None,
            score=DECISION_SCORE.get(action), value=action, comment=decision.get("comment") or None,
            correction={"answer": decision["answer"]} if action == "edit" and decision.get("answer") else None,
            source_info={"reviewer": decision.get("reviewer", ""), "ref": result.get("ref", ""),
                         "pipeline_status": result.get("status", ""), "confidence": result.get("confidence", "")})
        return True
    except Exception:                                    # observability must never break a review
        return False
