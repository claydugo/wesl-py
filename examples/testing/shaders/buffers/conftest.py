from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import wesl
    from wesl.testing import Buffer


@pytest.fixture(params=[0.5, 2.0], ids=["half_gain", "double_gain"])
def wesl_constants(request: pytest.FixtureRequest) -> dict[str, float]:
    return {"gain": request.param}


@pytest.fixture
def wesl_resources(
    wesl_options: wesl.CompileOptions, wesl_constants: dict[str, float]
) -> dict[tuple[int, int], Buffer]:
    import numpy as np  # noqa: PLC0415
    from wesl.testing import Buffer  # noqa: PLC0415

    values = np.array([-0.25, 0.0, 0.25, 0.75, 1.0], dtype=np.float32)
    expected = values * 2
    if wesl_options.features.flags["clamped"]:
        expected = np.clip(expected, 0, 1)
    expected *= wesl_constants["gain"]
    return {(0, 0): Buffer(data=values), (0, 1): Buffer(data=expected)}
