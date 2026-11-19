"""Deterministic product matching across systems.

Every system in a company names the same product a little differently.
This module decides, for each incoming record, which canonical product it is —
without a language model in the identity path. The same input always produces
the same answer, and every answer says which stage produced it and why.

Stages, tried in order (first hit wins):

=====  ==========================================  ===========
Stage  Rule                                        Result
=====  ==========================================  ===========
1      same master code                            CONFIRMED
2      same parent product + same normalised name  CONFIRMED
3      same normalised name                        PROBABLE
4      similarity >= threshold AND numbers agree   PROBABLE
=====  ==========================================  ===========

Guards:

* **Numeric guard** — if the names are similar but their grade numbers differ
  ("DDR4 16GB" vs "DDR4 32GB"), the result is CONFLICT, never a match.
* **Ambiguity guard** — if a soft stage (3 or 4) finds two or more equally good
  candidates, the result is CONFLICT instead of picking one silently.
* Nothing found -> ORPHAN.

Only CONFIRMED results may ever become writes; see :mod:`entity_matcher.gate`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Iterable, Optional

from .normalize import extract_numbers, normalize

DEFAULT_THRESHOLD = 0.88


class MatchState(str, Enum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    CONFLICT = "conflict"
    ORPHAN = "orphan"

    @property
    def writable(self) -> bool:
        return self is MatchState.CONFIRMED


@dataclass(frozen=True)
class Canonical:
    """A product in the master catalogue."""

    id: str
    name: str
    master_code: Optional[str] = None
    parent: Optional[str] = None


@dataclass(frozen=True)
class Record:
    """A product as one source system knows it."""

    source: str
    ref: str
    name: str
    master_code: Optional[str] = None
    parent: Optional[str] = None


@dataclass(frozen=True)
class Match:
    record: Record
    state: MatchState
    canonical_id: Optional[str]
    stage: Optional[int]
    score: float
    reason: str
    candidates: tuple[str, ...] = field(default_factory=tuple)

    @property
    def writable(self) -> bool:
        return self.state.writable


def similarity(a: str, b: str) -> float:
    """Similarity of two *normalised* names, 0..1."""
    return SequenceMatcher(None, a, b).ratio()


class Matcher:
    """Matches records against a catalogue of canonical products."""

    def __init__(self, catalogue: Iterable[Canonical], threshold: float = DEFAULT_THRESHOLD):
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be in (0, 1]")
        self.threshold = threshold
        self.catalogue: list[Canonical] = list(catalogue)
        ids = [c.id for c in self.catalogue]
        if len(ids) != len(set(ids)):
            raise ValueError("canonical ids must be unique")

        self._by_code: dict[str, Canonical] = {}
        self._by_name: dict[str, list[Canonical]] = {}
        self._norm: dict[str, str] = {}
        self._nums: dict[str, tuple[str, ...]] = {}
        for c in self.catalogue:
            if c.master_code:
                if c.master_code in self._by_code:
                    raise ValueError(f"duplicate master code {c.master_code!r}")
                self._by_code[c.master_code] = c
            key = normalize(c.name)
            self._norm[c.id] = key
            self._nums[c.id] = extract_numbers(c.name)
            self._by_name.setdefault(key, []).append(c)

    # ------------------------------------------------------------------ stages
    def match(self, record: Record) -> Match:
        key = normalize(record.name)
        nums = extract_numbers(record.name)

        # Stage 1 — master code
        if record.master_code and record.master_code in self._by_code:
            c = self._by_code[record.master_code]
            return Match(record, MatchState.CONFIRMED, c.id, 1, 1.0, "same master code")

        # Stage 2 — parent product + normalised name
        if record.parent:
            hits = [c for c in self._by_name.get(key, []) if c.parent == record.parent]
            if len(hits) == 1:
                return Match(record, MatchState.CONFIRMED, hits[0].id, 2, 1.0,
                             "same parent product and normalised name")

        # Stage 3 — identical normalised name
        hits = self._by_name.get(key, [])
        if len(hits) == 1:
            return Match(record, MatchState.PROBABLE, hits[0].id, 3, 1.0,
                         "identical normalised name")
        if len(hits) > 1:
            return Match(record, MatchState.CONFLICT, None, 3, 1.0,
                         "several canonicals share this name",
                         tuple(sorted(c.id for c in hits)))

        # Stage 4 — fuzzy name with numeric guard
        scored = sorted(
            ((similarity(key, self._norm[c.id]), c) for c in self.catalogue),
            key=lambda pair: (-pair[0], pair[1].id),
        )
        above = [(s, c) for s, c in scored if s >= self.threshold]
        if not above:
            best = scored[0][0] if scored else 0.0
            return Match(record, MatchState.ORPHAN, None, None, round(best, 4),
                         "no candidate above threshold")

        agreeing = [(s, c) for s, c in above if self._nums[c.id] == nums]
        if not agreeing:
            s, c = above[0]
            return Match(record, MatchState.CONFLICT, None, 4, round(s, 4),
                         f"numeric guard: {nums} != {self._nums[c.id]} ({c.id})",
                         (c.id,))

        top = agreeing[0][0]
        tied = [c for s, c in agreeing if s == top]
        if len(tied) > 1:
            return Match(record, MatchState.CONFLICT, None, 4, round(top, 4),
                         "ambiguous: equally similar candidates",
                         tuple(c.id for c in tied))
        return Match(record, MatchState.PROBABLE, tied[0].id, 4, round(top, 4),
                     "similar name, numbers agree")

    def match_all(self, records: Iterable[Record]) -> list[Match]:
        return [self.match(r) for r in records]


def summarize(matches: Iterable[Match]) -> dict[str, int]:
    """Count results per state, always returning all four keys."""
    out = {s.value: 0 for s in MatchState}
    for m in matches:
        out[m.state.value] += 1
    return out
