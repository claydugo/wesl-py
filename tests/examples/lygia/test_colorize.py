from importlib import import_module
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path

    import wgpu


def test_upstream_imports(wesl_compiler: wesl.Compiler) -> None:
    result = wesl_compiler.compile_source(
        "import examples::lygia::colorize::colorize; "
        "@compute @workgroup_size(1) fn main() { let rgba = colorize(0.5, 0.0, 1.0); }",
    )
    assert {
        "lygia::color::palette::heatmap",
        "lygia::math::map",
    } <= set(result.modules)
    assert "public " not in result.sources["lygia::color::palette::heatmap"].text


@pytest.mark.gpu
@pytest.mark.parametrize("shape", [(1, 1), (3, 65)])
def test_colorize(
    wesl_device: "wgpu.GPUDevice", shape: tuple[int, int], library_directory: "Path"
) -> None:
    numpy = pytest.importorskip("numpy")
    colorize = import_module("examples.lygia.compute").colorize
    values = numpy.linspace(-1, 3, shape[0] * shape[1], dtype=numpy.float32).reshape(
        shape
    )
    values = values[:, ::-1]
    actual = colorize(
        wesl_device,
        values,
        library_directory=library_directory,
        minimum=0.2,
        maximum=1.7,
    )
    fraction = numpy.clip((values.astype(numpy.float64) - 0.2) / 1.5, 0, 1)
    expected = numpy.ones((*shape, 4), dtype=numpy.float64)
    expected[..., :3] = numpy.clip(
        1 - (fraction[..., None] * 2.1 - [1.8, 1.14, 0.3]) ** 2, 0, 1
    )
    numpy.testing.assert_allclose(actual, expected, atol=5e-7, rtol=2e-6)


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [(1.0, 1.0), (1.0, 1.0000000001), (-3e38, 3e38), (1e40, 2e40)],
)
def test_invalid_display_range(
    wesl_device: "wgpu.GPUDevice",
    minimum: float,
    maximum: float,
    library_directory: "Path",
) -> None:
    numpy = pytest.importorskip("numpy")
    colorize = import_module("examples.lygia.compute").colorize
    with pytest.raises(ValueError, match="finite positive f32 range"):
        colorize(
            wesl_device,
            numpy.ones((1, 1), dtype=numpy.float32),
            library_directory=library_directory,
            minimum=minimum,
            maximum=maximum,
        )


@pytest.mark.gpu
def test_microscope_image(
    wesl_device: "wgpu.GPUDevice", library_directory: "Path"
) -> None:
    numpy = pytest.importorskip("numpy")
    colorize = import_module("examples.lygia.compute").colorize
    values = numpy.full((2048, 2048), 0.5, dtype=numpy.float32)
    actual = colorize(wesl_device, values, library_directory=library_directory)
    numpy.testing.assert_allclose(
        actual,
        numpy.broadcast_to([0.4375, 0.9919, 0.4375, 1.0], actual.shape),
        atol=5e-7,
        rtol=2e-6,
    )
