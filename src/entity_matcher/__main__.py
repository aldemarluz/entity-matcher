"""Command line: match a CSV of incoming records against a catalogue CSV.

    python -m entity_matcher examples/catalogue.csv examples/incoming.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys

from .matcher import Canonical, Matcher, Record, summarize


def _load_catalogue(path: str) -> list[Canonical]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [Canonical(r["id"], r["name"], r.get("master_code") or None, r.get("parent") or None)
                for r in csv.DictReader(fh)]


def _load_records(path: str) -> list[Record]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [Record(r["source"], r["ref"], r["name"], r.get("master_code") or None,
                       r.get("parent") or None) for r in csv.DictReader(fh)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="entity_matcher")
    ap.add_argument("catalogue")
    ap.add_argument("incoming")
    ap.add_argument("--threshold", type=float, default=0.88)
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    args = ap.parse_args(argv)

    matcher = Matcher(_load_catalogue(args.catalogue), threshold=args.threshold)
    results = matcher.match_all(_load_records(args.incoming))

    if args.json:
        json.dump([{
            "source": m.record.source, "ref": m.record.ref, "name": m.record.name,
            "state": m.state.value, "canonical": m.canonical_id, "stage": m.stage,
            "score": m.score, "reason": m.reason, "writable": m.writable,
        } for m in results], sys.stdout, indent=2)
        print()
        return 0

    width = max(len(m.record.name) for m in results) if results else 10
    idw = max(len(f"{m.record.source}:{m.record.ref}") for m in results) if results else 10
    for m in results:
        rid = f"{m.record.source}:{m.record.ref}"
        print(f"{rid:<{idw}}  {m.record.name:<{width}}  "
              f"{m.state.value:<9} {str(m.canonical_id or '-'):<8} stage={m.stage or '-'}  {m.reason}")
    print("\nsummary:", summarize(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
