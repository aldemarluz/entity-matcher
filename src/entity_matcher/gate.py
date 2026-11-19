"""The write gate: the only path from a match to a change in a real system.

Matching is allowed to be uncertain. Writing is not. This module enforces,
in code, three rules:

1. **Only CONFIRMED matches can produce a write.** PROBABLE, CONFLICT and
   ORPHAN results go to a review queue; trying to write them raises.
2. **Dry-run is the default.** An :class:`Executor` built without
   ``dry_run=False`` reports what it *would* do and changes nothing.
3. **Writes are idempotent.** Each write has a key derived from its content;
   applying the same proposal twice changes the target once.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, MutableMapping, Optional

from .matcher import Match, MatchState


class NotWritable(Exception):
    """Raised when something other than a CONFIRMED match is about to be written."""


@dataclass(frozen=True)
class Proposal:
    """A change someone (a person, a job, an AI agent) wants to make."""

    match: Match
    field_name: str
    value: Any
    proposed_by: str = "unknown"

    @property
    def key(self) -> str:
        payload = {
            "source": self.match.record.source,
            "ref": self.match.record.ref,
            "canonical": self.match.canonical_id,
            "field": self.field_name,
            "value": self.value,
        }
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class Outcome:
    applied: list[str] = field(default_factory=list)      # proposal keys written
    skipped_duplicate: list[str] = field(default_factory=list)
    queued_for_review: list[Proposal] = field(default_factory=list)
    dry_run: bool = True


def split(proposals: Iterable[Proposal]) -> tuple[list[Proposal], list[Proposal]]:
    """Separate writable proposals from those that need a human."""
    writable, review = [], []
    for p in proposals:
        (writable if p.match.state is MatchState.CONFIRMED else review).append(p)
    return writable, review


def assert_writable(p: Proposal) -> None:
    if p.match.state is not MatchState.CONFIRMED:
        raise NotWritable(
            f"{p.match.record.source}:{p.match.record.ref} is {p.match.state.value}; "
            "only confirmed matches can be written"
        )
    if p.match.canonical_id is None:  # defensive: confirmed always has an id
        raise NotWritable("confirmed match without canonical id")


class Executor:
    """Applies proposals to a target store, deterministically and idempotently.

    ``target`` is any mutable mapping ``canonical_id -> {field: value}``;
    in production it would be an adapter over a real system's API.
    """

    def __init__(self, target: MutableMapping[str, dict], dry_run: bool = True,
                 ledger: Optional[set[str]] = None):
        self.target = target
        self.dry_run = dry_run
        self.ledger: set[str] = ledger if ledger is not None else set()
        self.audit: list[dict] = []

    def apply(self, proposals: Iterable[Proposal]) -> Outcome:
        writable, review = split(proposals)
        out = Outcome(queued_for_review=review, dry_run=self.dry_run)
        for p in writable:
            assert_writable(p)
            if p.key in self.ledger:
                out.skipped_duplicate.append(p.key)
                continue
            before = self.target.get(p.match.canonical_id, {}).get(p.field_name)
            entry = {
                "key": p.key,
                "canonical": p.match.canonical_id,
                "field": p.field_name,
                "before": before,
                "after": p.value,
                "proposed_by": p.proposed_by,
                "dry_run": self.dry_run,
            }
            if not self.dry_run:
                self.target.setdefault(p.match.canonical_id, {})[p.field_name] = p.value
                self.ledger.add(p.key)
            self.audit.append(entry)
            out.applied.append(p.key)
        return out
