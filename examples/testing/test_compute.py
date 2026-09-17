import numpy as np
import pytest
import wesl
from wesl.testing import Buffer, ShaderRunner


@pytest.mark.gpu
@pytest.mark.parametrize("element_count", [1, 4, 6, 9])
def test_weighted_levels(
    wesl_compiler: wesl.Compiler, wesl_runner: ShaderRunner, element_count: int
) -> None:
    shader = wesl_compiler.compile_file("combine.wesl")
    values = np.arange(element_count, dtype=np.float32) / 4 - 0.25
    weights = np.linspace(0.5, 2, element_count, dtype=np.float32)
    output = wesl_runner.compute(
        shader,
        resources={
            (0, 0): Buffer(data=values),
            (0, 1): Buffer(data=weights),
            (0, 2): Buffer(data=np.full_like(values, np.nan)),
            (0, 3): Buffer(data=np.full_like(values, np.nan)),
        },
        workgroups=(element_count + 3) // 4,
    )
    expected_weighted = values * weights
    expected_adjusted = expected_weighted * 2
    if wesl_compiler.options.features.flags["clamped"]:
        expected_adjusted = np.clip(expected_adjusted, 0, 1)
    np.testing.assert_array_equal(output[0, 2], expected_weighted)
    np.testing.assert_array_equal(output[0, 3], expected_adjusted)
