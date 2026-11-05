"""Settings for the questionnaire responder. Defaults are the values tuned in runs 4-7."""
from dataclasses import dataclass, field

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"
JEV = "jev-latest"

# USD per million tokens (input, output). Claude: Anthropic list prices, Nov 2026 (Haiku: prompts under
# 100k tokens). Jev: TypeSafe's published price; output tokens are currently free.
PRICES = {OPUS: (4.00, 20.00), SONNET: (2.00, 10.00), HAIKU: (0.10, 0.50), "jev": (0.042, 0.0)}

ESCALATE_TEXT = "Not covered by policy, escalate"


@dataclass
class Settings:
    draft_model: str = SONNET          # the only model that writes customer-facing text
    extract_model: str = HAIKU         # splits answers into claims with verbatim quotes
    jev_model: str = JEV
    search_k: int = 6                  # sections pulled by full-text search before the Jev gate
    max_parallel: int = 6              # questions answered at once
    jev_workers: int = 8               # parallel Jev requests

    # Claim-based confidence rules (same as the baseline).
    high_min_support: float = 1.0      # share of claims backed by a cited section
    high_min_explicit: float = 1.0     # share of claims judged "supports" with high confidence
    medium_min_support: float = 0.75

    # Jev thresholds (starting points from TypeSafe's docs, tuned in runs 4 and 6).
    yes: float = 0.7                   # a commitment check above this = restricted
    no: float = 0.4                    # between `no` and `yes` = uncertain, capped at Medium
    gate_relevant: float = 0.45        # a section must be on topic...
    gate_evidence: float = 0.55        # ...and hold usable evidence to reach the writer
    complete: float = 0.6              # sections together answer every part of the question
    support_conf: float = 0.8          # confidence needed to accept "supports" without a human
    note_hold: float = 0.7             # reviewer note asks for a check before sending

    # Answer library.
    library_match: float = 0.8         # Jev probability that two questions ask for the same thing
    add_auto_to_library: bool = False  # False: only human-approved answers enter the library

    auto_approve_levels: set = field(default_factory=lambda: {"High"})
