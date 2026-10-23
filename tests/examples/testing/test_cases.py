from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from wesl.testing import run_test

if TYPE_CHECKING:
    import wesl
    import wgpu


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(0.0, 0.0, id="black"),
        pytest.param(0.25, 0.5, id="shadow"),
        pytest.param(0.5, 1.0, id="white-point"),
    ],
)
def test_adjust(
    wesl_device: wgpu.GPUDevice,
    wesl_compiler: wesl.Compiler,
    wesl_test_options: wesl.TestOptions,
    value: float,
    expected: float,
) -> None:
    run_test(
        wesl_device,
        wesl_compiler,
        "adjusts_value",
        root="package::tests::examples::testing::shaders::levels_cases",
        options=wesl_test_options,
        constants={"value": value, "expected": expected},
    )
