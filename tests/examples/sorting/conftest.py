from pathlib import Path

import pytest


@pytest.fixture(
    params=sorted((Path(__file__).parents[3] / "examples/sorting/keys").glob("*.wesl")),
    ids=lambda key: key.stem,
)
def key(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture
def wesl_modules(key: Path) -> dict[str, str]:
    return {"package::examples::sorting::key": key.read_text()}


@pytest.fixture
def wesl_filenames(key: Path) -> dict[str, Path]:
    return {"package::examples::sorting::key": key}
