from __future__ import annotations

from pathlib import Path

import pytest

from pdf_figures.paths import AllowedRoots, PathNotAllowed


def test_resolves_inside_root(tmp_path: Path):
    allowed = tmp_path / "uploads"
    allowed.mkdir()
    target = allowed / "paper.pdf"
    target.write_bytes(b"%PDF-1.7")
    roots = AllowedRoots([allowed])
    assert roots.resolve(target) == target.resolve()


def test_rejects_outside_root(tmp_path: Path):
    allowed = tmp_path / "uploads"
    allowed.mkdir()
    outside = tmp_path / "elsewhere.pdf"
    outside.write_bytes(b"%PDF-1.7")
    with pytest.raises(PathNotAllowed, match="outside the allowed roots"):
        AllowedRoots([allowed]).resolve(outside)


def test_rejects_relative(tmp_path: Path):
    with pytest.raises(PathNotAllowed, match="absolute path"):
        AllowedRoots([tmp_path]).resolve("paper.pdf")


def test_rejects_missing(tmp_path: Path):
    with pytest.raises(PathNotAllowed, match="not found"):
        AllowedRoots([tmp_path]).resolve(tmp_path / "missing.pdf")


def test_rejects_empty_roots(tmp_path: Path):
    target = tmp_path / "paper.pdf"
    target.write_bytes(b"%PDF-1.7")
    with pytest.raises(PathNotAllowed, match="no allowed roots"):
        AllowedRoots([]).resolve(target)
