from pathlib import Path

import pytest
import wesl


@pytest.fixture(params=[False, True], ids=["plain", "residual"])
def wesl_options(request: pytest.FixtureRequest) -> wesl.CompileOptions:
    return wesl.CompileOptions(
        features=wesl.Features(flags={"residual": request.param})
    )


@pytest.fixture
def wesl_root_directory() -> Path:
    return Path(__file__).parents[3]


@pytest.fixture
def wesl_resources(wesl_options: wesl.CompileOptions) -> dict:
    numpy = pytest.importorskip("numpy")
    testing = pytest.importorskip("wesl.testing")
    resources = {(0, 0): testing.Buffer(data=numpy.array([2, -2], dtype=numpy.float32))}
    if wesl_options.features.flags["residual"]:
        resources[0, 1] = testing.Buffer(data=numpy.array([1, -1], dtype=numpy.float32))
    return resources


@pytest.fixture
def wesl_constants() -> dict[str, float]:
    return {"0": 2, "1": 0.25}
