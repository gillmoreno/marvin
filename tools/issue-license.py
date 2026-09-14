#!/usr/bin/env python3
"""Mint a Marvin Enterprise JWT. Run this on our machine; customers never run it.

The private key is not in the repo. Default path: ~/.marvin-pilot/license-private.pem
(created once; back it up). The matching public key is worker/marvin/license.pub.

  cd worker && uv run python ../tools/issue-license.py --company example.com --expires 2027-11-01 --seats 50
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))

from marvin.license import FEATURES, issue  # noqa: E402

DEFAULT_KEY = Path.home() / ".marvin-pilot" / "license-private.pem"


def main() -> int:
    p = argparse.ArgumentParser(description="Issue a Marvin Enterprise license JWT")
    p.add_argument("--company", required=True, help="who it is for (example.com)")
    p.add_argument("--expires", required=True, help="last valid day, YYYY-MM-DD (UTC)")
    p.add_argument("--seats", type=int, default=10)
    p.add_argument("--features", default="*", help="comma list or * (all). Known: " + ", ".join(FEATURES))
    p.add_argument(
        "--key",
        type=Path,
        default=Path(os.environ.get("MARVIN_LICENSE_PRIVATE_KEY_FILE") or DEFAULT_KEY),
        help=f"private key PEM (default {DEFAULT_KEY})",
    )
    args = p.parse_args()
    if not args.key.is_file():
        print(
            f"no private key at {args.key}\n"
            "this file is not in the repo; it lives on the machine that issues keys.",
            file=sys.stderr,
        )
        return 2
    token = issue(args.company, args.expires, args.seats, args.features, private_pem=args.key.read_bytes())
    print(f"{args.company} · {args.seats} seats · until {args.expires}", file=sys.stderr)
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
