"""Generate the synthetic fixture PDFs for manual inspection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from fixtures import build_all  # noqa: E402


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures")
    for name, path in build_all(target).items():
        print(f"{name:14} {path}")


if __name__ == "__main__":
    main()
