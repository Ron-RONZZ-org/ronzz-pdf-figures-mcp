from __future__ import annotations

from pathlib import Path

import pytest

from . import fixtures as fixture_builders


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return fixture_builders.build_all(tmp_path_factory.mktemp("pdf-fixtures"))
