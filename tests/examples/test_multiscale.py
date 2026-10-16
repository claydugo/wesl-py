from importlib import import_module

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pygfx")
get_shared = import_module("pygfx.renderers.wgpu").get_shared
enhance = import_module("examples.multiscale.compute").enhance


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("case", "sigma"),
    [
        pytest.param("single-pixel", 0.7, id="single-pixel"),
        pytest.param("impulses", 3.0, id="impulses"),
        pytest.param("non-square", 12.0, id="wide-kernel"),
    ],
)
def test_enhancement_matches_gaussian_reference(case: str, sigma: float) -> None:
    device = get_shared().device
    if case == "single-pixel":
        channels = np.array([0.25, 0.5, 0.75], dtype=np.float32).reshape(3, 1, 1)
    elif case == "impulses":
        channels = np.zeros((3, 19, 37), dtype=np.float32)
        channels[0] = 0.25
        channels[1, 0, 0] = 1
        channels[1, -1, -1] = 1
        channels[2, 9, 18] = 1
    else:
        channels = np.random.default_rng(42).random((3, 67, 71), dtype=np.float32)

    references = []
    for deviation in (sigma, sigma * 2):
        radius = int(np.ceil(3 * deviation))
        offsets = np.arange(-radius, radius + 1, dtype=np.float64)
        coefficients = np.exp(-0.5 * (offsets / deviation) ** 2)
        coefficients /= coefficients.sum()
        reference = channels[1:].astype(np.float64)
        for axis in (2, 1):
            padding = [(0, 0), (0, 0), (0, 0)]
            padding[axis] = (radius, radius)
            padded = np.pad(reference, padding, mode="edge")
            reference = np.apply_along_axis(
                lambda values, weights=coefficients: np.convolve(
                    values, weights, mode="valid"
                ),
                axis,
                padded,
            )
        references.append(reference)
    expected = channels.copy()
    expected[1:] = np.clip(channels[1:] + 1.5 * (references[0] - references[1]), 0, 1)
    buffers = enhance(channels, sigma, 1.5)
    _, fine, coarse, output = buffers
    try:
        for buffer, reference in zip((fine, coarse), references, strict=True):
            actual = np.frombuffer(
                device.queue.read_buffer(buffer), dtype=np.float32
            ).reshape(channels.shape)
            np.testing.assert_allclose(actual[1:], reference, rtol=3e-5, atol=2e-6)
        actual = np.frombuffer(
            device.queue.read_buffer(output), dtype=np.float32
        ).reshape(channels.shape)
        np.testing.assert_array_equal(actual[0], channels[0])
        np.testing.assert_allclose(actual, expected, rtol=3e-5, atol=2e-6)
    finally:
        for buffer in buffers:
            buffer.destroy()
