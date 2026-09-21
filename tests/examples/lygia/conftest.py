from pathlib import Path

import pytest


@pytest.fixture
def library_directory() -> Path:
    return Path(__file__).parents[3] / ".wesl/lygia"


@pytest.fixture
def wesl_dependencies(
    wesl_dependencies: dict[str, Path], library_directory: Path
) -> dict[str, Path]:
    return {
        **wesl_dependencies,
        "lygia": library_directory,
    }


@pytest.fixture
def wesl_root_directory() -> Path:
    return Path(__file__).parents[3]
