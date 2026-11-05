"""AI security questionnaire responder: grounded answers from a policy pack, Jev decisions, human review."""
from .config import ESCALATE_TEXT, Settings
from .retrieval import PolicyIndex

__version__ = "1.0.0"
__all__ = ["Settings", "PolicyIndex", "ESCALATE_TEXT", "Responder", "AnswerLibrary"]


def __getattr__(name):            # heavy imports (LangGraph, Anthropic, TypeSafe) only when needed
    if name == "Responder":
        from .graph import Responder
        return Responder
    if name == "AnswerLibrary":
        from .library import AnswerLibrary
        return AnswerLibrary
    raise AttributeError(name)
