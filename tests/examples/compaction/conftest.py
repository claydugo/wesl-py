import pytest
import wesl


@pytest.fixture(params=[False, True], ids=["at_least", "below"])
def wesl_features(request: pytest.FixtureRequest) -> wesl.Features:
    return wesl.Features(flags={"keep_below": request.param})


@pytest.fixture(params=[500, 2**31], ids=["threshold_500", "threshold_2_31"])
def wesl_constants(request: pytest.FixtureRequest) -> dict[str, float]:
    return {"0": request.param}
