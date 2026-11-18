"""Allowed-root path guard, mirroring the wiki writer's uploadDirs contract."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class PathNotAllowed(ValueError):
    """A caller-supplied path is missing, relative or outside the allowlist."""


class AllowedRoots:
    def __init__(self, roots: Iterable[str | Path]) -> None:
        self.roots = tuple(Path(root).resolve() for root in roots if str(root).strip())

    def resolve(self, filepath: str | Path) -> Path:
        if not str(filepath).strip():
            raise PathNotAllowed("provide a non-empty absolute path.")
        path = Path(filepath)
        if not path.is_absolute():
            raise PathNotAllowed(f"provide an absolute path (got {str(filepath)!r}).")
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError as error:
            raise PathNotAllowed(f"file not found at {str(filepath)!r}.") from error
        if not self.roots:
            raise PathNotAllowed(
                "no allowed roots are configured; set PDF_FIGURES_ALLOWED_ROOTS "
                "to the readable upload directories."
            )
        for root in self.roots:
            if resolved == root or root in resolved.parents:
                return resolved
        raise PathNotAllowed(
            f"path {str(resolved)!r} is outside the allowed roots "
            f"({', '.join(str(root) for root in self.roots)}). "
            "A symlink may have resolved outside the allowlist."
        )
