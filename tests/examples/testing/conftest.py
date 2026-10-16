import pytest
import wesl


@pytest.fixture(params=[False, True], ids=["linear", "clamped"])
def wesl_features(request: pytest.FixtureRequest) -> wesl.Features:
    return wesl.Features(flags={"clamped": request.param})
