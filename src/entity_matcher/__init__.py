"""entity-matcher: deterministic product matching with a write gate."""

from .gate import Executor, NotWritable, Outcome, Proposal, split
from .matcher import Canonical, Match, Matcher, MatchState, Record, similarity, summarize
from .normalize import extract_numbers, normalize

__all__ = [
    "Canonical", "Record", "Match", "Matcher", "MatchState", "similarity", "summarize",
    "normalize", "extract_numbers",
    "Proposal", "Executor", "Outcome", "NotWritable", "split",
]

__version__ = "1.0.0"
