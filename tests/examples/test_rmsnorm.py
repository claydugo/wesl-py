from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
import wesl

if TYPE_CHECKING:
    import wgpu

numpy = pytest.importorskip("numpy")
pytest.importorskip("wgpu")
compute_with_buffers = import_module("wgpu.utils.compute").compute_with_buffers
normalize = import_module("examples.rmsnorm.compute").normalize


@pytest.fixture(params=[False, True], ids=["plain", "residual"])
def wesl_options(request: pytest.FixtureRequest) -> wesl.CompileOptions:
    return wesl.CompileOptions(
        features=wesl.Features(flags={"residual": request.param})
    )


@pytest.fixture
def wesl_root_directory() -> Path:
    return Path(__file__).parents[2] / "examples"


@pytest.mark.gpu
@pytest.mark.parametrize("width", [1, 63, 64, 65, 1025])
@pytest.mark.parametrize("epsilon", [1e-6, 0.25])
def test_normalize(
    wesl_compiler: wesl.Compiler,
    width: int,
    epsilon: float,
) -> None:
    random = numpy.random.default_rng(7)
    values = random.normal(size=(3, width)).astype(numpy.float32)
    values[0] = 0
    residual = random.normal(size=values.shape).astype(numpy.float32)
    residual[0] = 0
    weights = numpy.linspace(-1, 2, width, dtype=numpy.float32)
    resources = {
        0: values,
        2: weights,
        3: numpy.full_like(values, numpy.nan),
    }
    if wesl_compiler.options.features.flags["residual"]:
        resources[1] = residual
        combined = (values + residual).astype(numpy.float64)
    else:
        combined = values.astype(numpy.float64)
    expected = (
        combined
        / numpy.sqrt(numpy.mean(combined**2, axis=1, keepdims=True) + epsilon)
        * weights
    )
    output = compute_with_buffers(
        resources,
        {3: (3, width, "f")},
        wesl_compiler.compile_file("rmsnorm/normalize.wesl").wgsl,
        n=3,
        constants={"0": width, "1": epsilon},
    )
    numpy.testing.assert_allclose(output[3], expected, rtol=2e-5, atol=2e-6)


@pytest.mark.gpu
@pytest.mark.parametrize("residual", [None, [[0.5, -1, 2], [0.25, 0, -0.5]]])
def test_normalize_driver(
    wesl_device: wgpu.GPUDevice, residual: list[list[float]] | None
) -> None:
    values = numpy.array([[1, -4], [-2, 5], [3, 6]], dtype=numpy.float32).T
    weights = numpy.array([0.5, 0, -1, 0, 2], dtype=numpy.float32)[::2]
    if residual is not None:
        residual = numpy.array(residual, dtype=numpy.float32)
    output = normalize(wesl_device, values, weights, residual=residual)
    combined = values.astype(numpy.float64)
    if residual is not None:
        combined += residual
    expected = (
        combined
        / numpy.sqrt(numpy.mean(combined**2, axis=1, keepdims=True) + 1e-6)
        * weights
    )
    assert output.dtype == numpy.float32
    numpy.testing.assert_allclose(output, expected, rtol=2e-5)


@pytest.mark.parametrize(
    ("values", "weights", "residual", "epsilon", "message"),
    [
        ([], [1], None, 1e-6, "nonempty matrix"),
        ([[]], [], None, 1e-6, "nonempty matrix"),
        ([[1, 2, 3]], [1, 2], None, 1e-6, "one weight per column"),
        ([[1]], [[1]], None, 1e-6, "one weight per column"),
        ([[1, 2]], [1, 2], [[1], [2]], 1e-6, "same shape"),
        ([[1]], [1], None, 0, "finite and at least"),
        ([[1]], [1], None, float("nan"), "finite and at least"),
        ([[0]], [1], None, 2**-149, "finite and at least"),
    ],
)
def test_invalid_inputs(values, weights, residual, epsilon, message) -> None:  # noqa: ANN001
    with pytest.raises(ValueError, match=message):
        normalize(
            cast("wgpu.GPUDevice", None),
            numpy.array(values, dtype=numpy.float32),
            numpy.array(weights, dtype=numpy.float32),
            residual=None
            if residual is None
            else numpy.array(residual, dtype=numpy.float32),
            epsilon=epsilon,
        )


@pytest.mark.gpu
def test_smallest_epsilon(wesl_device: wgpu.GPUDevice) -> None:
    output = normalize(
        wesl_device,
        numpy.zeros((1, 2), dtype=numpy.float32),
        numpy.array([1, 2], dtype=numpy.float32),
        epsilon=2**-126,
    )
    numpy.testing.assert_array_equal(output, [[0, 0]])
