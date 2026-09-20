from importlib import import_module

import pytest

numpy = pytest.importorskip("numpy")
pytest.importorskip("pygfx")
get_shared = import_module("pygfx.renderers.wgpu").get_shared
load_colony = import_module("examples.common").load_colony
enhance = import_module("examples.multiscale.compute").enhance


@pytest.mark.gpu
def test_multiscale(pytestconfig: pytest.Config) -> None:
    device = get_shared().device

    impulses = numpy.zeros((3, 19, 37), dtype=numpy.float32)
    impulses[0] = 0.25
    impulses[1, 0, 0] = 1
    impulses[1, -1, -1] = 1
    impulses[2, 9, 18] = 1
    random = numpy.random.default_rng(42)
    cases = [
        numpy.array([0.25, 0.5, 0.75], dtype=numpy.float32).reshape(3, 1, 1),
        impulses,
        random.random((3, 67, 71), dtype=numpy.float32),
    ]
    if pytestconfig.getoption("--image"):
        channels, _, _ = load_colony()
        cases.append(channels)

    for channels in cases:
        for sigma in (0.7, 3.0, 12.0):
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
            expected[1:] = numpy.clip(
                channels[1:] + 2 * (references[0] - references[1]), 0, 1
            )
            for tiled in (False, True):
                source, fine, coarse, output = enhance(  # noqa: RUF059
                    device, channels, sigma, 2.0, tiled=tiled
                )
                for buffer, reference in zip((fine, coarse), references, strict=True):
                    actual = numpy.frombuffer(
                        device.queue.read_buffer(buffer), dtype=numpy.float32
                    ).reshape(channels.shape)
                    numpy.testing.assert_allclose(
                        actual[1:], reference, rtol=3e-5, atol=2e-6
                    )
                actual = numpy.frombuffer(
                    device.queue.read_buffer(output), dtype=numpy.float32
                ).reshape(channels.shape)
                numpy.testing.assert_array_equal(actual[0], channels[0])
                numpy.testing.assert_allclose(actual, expected, rtol=3e-5, atol=2e-6)
