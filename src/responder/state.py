"""Graph state and the structured outputs Claude must return."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class DraftAnswer(BaseModel):
    covered: bool = Field(description="False if the passages do not answer the question.")
    answer: str = Field(description="The answer as the vendor would write it. Empty if not covered.")
    cited_section_ids: list[str] = Field(description="Section IDs the answer relies on, e.g. ['AIG-3'].")
    reviewer_note: str = Field(description=(
        "Internal note for the human reviewer: gaps, caveats or assumptions, e.g. 'policy does not mention "
        "service credits'. Never shown to the customer. '' if there is nothing to flag."))


class ExtractedClaim(BaseModel):
    claim: str = Field(description="One factual statement taken from the answer.")
    cited_section_id: str = Field(description="The one section that supports it, or '' if none.")
    evidence_quote: str = Field(description="Exact words copied from that section that support the claim, or ''.")


class ClaimList(BaseModel):
    claims: list[ExtractedClaim]


class JudgeVerdict(BaseModel):
    """Used by the eval runner's LLM judge."""
    faithful: bool = Field(description="True if every statement in the answer is supported by the cited sections.")
    unsupported: list[str] = Field(description="Statements in the answer that the sections do not support.")


class QState(TypedDict, total=False):
    """State of the per-question graph."""
    question: str
    classification: dict
    restricted: bool
    restricted_reasons: list[str]
    caps: list[str]        # reasons that hold an answer at Medium (uncertain Jev answers, reviewer notes)
    library: dict          # library lookup result
    jev: dict              # raw Jev probabilities, logged to the audit trail
    search_log: list[str]
    passages: dict         # section_id -> passage
    draft: dict
    grounding: dict
    result: dict


class RunState(TypedDict):
    """State of the questionnaire-level graph: answer all -> human review -> finalise."""
    items: list
    results: Annotated[list, operator.add]
    decisions: list
    final: list
    summary: dict
