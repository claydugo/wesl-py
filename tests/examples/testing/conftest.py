from pathlib import Path

import pytest
import wesl


@pytest.fixture
def wesl_root_directory() -> Path:
    return Path(__file__).parent / "shaders"


@pytest.fixture(params=[False, True], ids=["linear", "clamped"])
def wesl_options(request: pytest.FixtureRequest) -> wesl.CompileOptions:
    return wesl.CompileOptions(
        features=wesl.Features(flags={"clamped": request.param}),
    )
