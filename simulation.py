"""Print the original, zero-phase symbolic field using ordinary Python."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from entropy import build_expression


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Display the original illustrative signed symbolic field."
    )
    parser.parse_args(argv)
    print(build_expression())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
