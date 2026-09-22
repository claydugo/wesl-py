import pytest
import wesl

np = pytest.importorskip("numpy")
compute_with_buffers = pytest.importorskip("wgpu.utils.compute").compute_with_buffers


@pytest.mark.gpu
@pytest.mark.parametrize(
    "element_count",
    [
        pytest.param(1, id="single-element"),
        pytest.param(4, id="full-workgroup"),
        pytest.param(9, id="partial-tail"),
    ],
)
def test_weighted_levels(wesl_compiler: wesl.Compiler, element_count: int) -> None:
    shader = wesl_compiler.compile_file("combine.wesl")
    values = np.arange(element_count, dtype=np.float32) / 4 - 0.25
    weights = np.linspace(0.5, 2, element_count, dtype=np.float32)
    output = compute_with_buffers(
        {
            0: values,
            1: weights,
            2: np.full_like(values, np.nan),
            3: np.full_like(values, np.nan),
        },
        {2: (element_count, "f"), 3: (element_count, "f")},
        shader.wgsl,
        n=(element_count + 3) // 4,
    )
    expected_weighted = values * weights
    expected_adjusted = expected_weighted * 2
    if wesl_compiler.options.features.flags["clamped"]:
        expected_adjusted = np.clip(expected_adjusted, 0, 1)
    np.testing.assert_array_equal(output[2], expected_weighted)
    np.testing.assert_array_equal(output[3], expected_adjusted)
