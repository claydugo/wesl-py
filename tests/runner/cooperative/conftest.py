import pytest
import wesl


@pytest.fixture
def wesl_constants() -> dict[str, float]:
    return {"lanes": 32, "5": 4294967295, "enabled": True, "offset": 7}


@pytest.fixture
def wesl_features() -> wesl.Features:
    return wesl.Features(flags={"qualified": True})
