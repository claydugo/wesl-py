import pytest
import wesl


@pytest.fixture
def wesl_features() -> wesl.Features:
    return wesl.Features(flags={"qualified": True})
