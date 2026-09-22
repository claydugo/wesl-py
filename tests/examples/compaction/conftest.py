from pathlib import Path

import pytest
import wesl


@pytest.fixture(params=[False, True], ids=["at_least", "below"])
def wesl_features(request: pytest.FixtureRequest) -> wesl.Features:
    return wesl.Features(flags={"keep_below": request.param})


@pytest.fixture
def wesl_root_directory() -> Path:
    return Path(__file__).parents[3]


@pytest.fixture
def wesl_constants() -> dict[str, float]:
    return {"0": 500}
