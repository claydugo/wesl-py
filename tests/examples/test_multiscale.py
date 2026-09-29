from importlib import import_module

import pytest

numpy = pytest.importorskip("numpy")
pytest.importorskip("pygfx")
get_shared = import_module("pygfx.renderers.wgpu").get_shared
load_colony = import_module("examples.multiscale.common").load_colony
enhance = import_module("examples.multiscale.compute").enhance


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("case", "sigma"),
    [
        pytest.param("single-pixel", 0.7, id="single-pixel"),
        pytest.param("impulses", 3.0, id="impulses"),
        pytest.param("non-square", 12.0, id="wide-kernel"),
        pytest.param("sample-tiff", 3.0, id="sample-tiff"),
    ],
)
def test_enhancement_matches_gaussian_reference(
    pytestconfig: pytest.Config, case: str, sigma: float
) -> None:
    device = get_shared().device
    if case == "single-pixel":
        channels = numpy.array([0.25, 0.5, 0.75], dtype=numpy.float32).reshape(3, 1, 1)
    elif case == "impulses":
        channels = numpy.zeros((3, 19, 37), dtype=numpy.float32)
        channels[0] = 0.25
        channels[1, 0, 0] = 1
        channels[1, -1, -1] = 1
        channels[2, 9, 18] = 1
    elif case == "non-square":
        channels = numpy.random.default_rng(42).random((3, 67, 71), dtype=numpy.float32)
    else:
        if not pytestconfig.getoption("--image"):
            pytest.skip("requires --image to load the sample TIFF")
        channels, _, _ = load_colony()

    references = []
    for deviation in (sigma, sigma * 2):
        radius = int(numpy.ceil(3 * deviation))
        offsets = numpy.arange(-radius, radius + 1, dtype=numpy.float64)
        coefficients = numpy.exp(-0.5 * (offsets / deviation) ** 2)
        coefficients /= coefficients.sum()
        reference = channels[1:].astype(numpy.float64)
        for axis in (2, 1):
            padding = [(0, 0), (0, 0), (0, 0)]
            padding[axis] = (radius, radius)
            padded = numpy.pad(reference, padding, mode="edge")
            reference = numpy.apply_along_axis(
                lambda values, weights=coefficients: numpy.convolve(
                    values, weights, mode="valid"
                ),
                axis,
                padded,
            )
        references.append(reference)
    expected = channels.copy()
    expected[1:] = numpy.clip(channels[1:] + 2 * (references[0] - references[1]), 0, 1)
    buffers = enhance(channels, sigma, 2.0)
    source, fine, coarse, output = buffers  # noqa: RUF059
    try:
        for buffer, reference in zip((fine, coarse), references, strict=True):
            actual = numpy.frombuffer(
                device.queue.read_buffer(buffer), dtype=numpy.float32
            ).reshape(channels.shape)
            numpy.testing.assert_allclose(actual[1:], reference, rtol=3e-5, atol=2e-6)
        actual = numpy.frombuffer(
            device.queue.read_buffer(output), dtype=numpy.float32
        ).reshape(channels.shape)
        numpy.testing.assert_array_equal(actual[0], channels[0])
        numpy.testing.assert_allclose(actual, expected, rtol=3e-5, atol=2e-6)
    finally:
        for buffer in buffers:
            buffer.destroy()
