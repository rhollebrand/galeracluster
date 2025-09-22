"""Command line interface to inspect the Hogebrug status."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, Optional

from .checker import BridgeStatusChecker, BridgeStatusError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Controleer de actuele status van de Hogebrug in Overschie."
    )
    parser.add_argument(
        "--bridge",
        default="Hogebrug",
        help="Naam van de brug waarvoor de status opgevraagd moet worden.",
    )
    parser.add_argument(
        "--dataset",
        default="brugopeningen",
        help="Naam van het dataset-id op het Rotterdam open data portaal.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=5,
        help="Aantal records dat opgehaald wordt om de status te bepalen.",
    )
    parser.add_argument(
        "--url",
        default="https://rotterdam.dataplatform.nl/api/records/1.0/search/",
        help="API-endpoint van het open data portaal.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Toon het resultaat als JSON in plaats van tekst.",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    checker = BridgeStatusChecker(
        dataset=args.dataset,
        bridge_name=args.bridge,
        base_url=args.url,
        rows=args.rows,
    )

    try:
        status = checker.get_status()
    except BridgeStatusError as exc:
        print(f"Kon de brugstatus niet bepalen: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    else:
        observed = status.observed_at.isoformat() if status.observed_at else "onbekend"
        print(f"De {args.bridge} is {status.label}. ({status.summary})")
        print(f"Laatste melding: {observed}")
        print(f"Bron: {status.source_url}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
