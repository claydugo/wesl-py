# ruff: noqa: PLR2004

from importlib import import_module

import pytest

numpy = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")
pytest.importorskip("pygfx")
get_shared = import_module("pygfx.renderers.wgpu").get_shared
compute = import_module("examples.multiscale.compute")

pytestmark = pytest.mark.gpu


def gaussian_reference(fields: numpy.ndarray, sigma: float) -> numpy.ndarray:
    radius = int(numpy.ceil(3 * sigma))
    offsets = numpy.arange(-radius, radius + 1, dtype=numpy.float64)
    weights = numpy.exp(-0.5 * (offsets / sigma) ** 2)
    weights /= weights.sum()
    result = fields.astype(numpy.float64)
    for axis in (2, 1):
        padding = [(0, 0), (0, 0), (0, 0)]
        padding[axis] = (radius, radius)
        result = numpy.apply_along_axis(
            lambda values: numpy.convolve(values, weights, mode="valid"),
            axis,
            numpy.pad(result, padding, mode="edge"),
        )
    return result


def test_foreground_correlation() -> None:
    device = get_shared().device
    channels = numpy.full((3, 19, 37), 0.02, dtype=numpy.float32)
    channels[0] = 1
    channels[0, 3:16, 7:30] = 0.5
    channels[1, 3:16, 7:30] = numpy.linspace(0.2, 0.8, 23)
    channels[2, 3:16, 7:30] = 1 - channels[1, 3:16, 7:30]
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result = compute.analyze(source, (37, 19), 2.1)
    actual = numpy.frombuffer(
        device.queue.read_buffer(result), dtype=numpy.float32
    ).reshape(19, 37, 2)
    gfp, rfp = channels[1:].astype(numpy.float64)
    foreground = channels[0] <= 0.9
    moments = gaussian_reference(
        numpy.array(
            [
                gfp * foreground,
                rfp * foreground,
                gfp**2 * foreground,
                rfp**2 * foreground,
                gfp * rfp * foreground,
                foreground,
            ]
        ),
        2.1,
    )
    moments[:5] /= numpy.maximum(moments[5], 1e-6)
    variance = moments[2:4] - moments[:2] ** 2
    expected = (moments[4] - moments[0] * moments[1])[foreground] / numpy.sqrt(
        variance[0][foreground] * variance[1][foreground]
    )
    numpy.testing.assert_allclose(actual[:, :, 0][foreground], expected, atol=1e-4)
    numpy.testing.assert_allclose(actual[:, :, 0][foreground], -1, atol=1e-4)
    numpy.testing.assert_array_equal(actual[:, :, 1], foreground)
    numpy.testing.assert_array_equal(actual[~foreground], 0)


def test_correlation_brightness_offsets() -> None:
    device = get_shared().device
    pattern = numpy.random.default_rng(917).random((2, 129, 129)) < 0.085
    pattern[1] = pattern[0]
    channels = numpy.full((3, 129, 129), 0.5, dtype=numpy.float32)
    channels[1:] = (227 + pattern.astype(numpy.float32)) / 255
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result = compute.analyze(source, (129, 129), 12)
    actual = numpy.frombuffer(
        device.queue.read_buffer(result), dtype=numpy.float32
    ).reshape(129, 129, 2)[36:-36, 36:-36]
    gfp, rfp = channels[1:].astype(numpy.float64)
    moments = gaussian_reference(
        numpy.array([gfp, rfp, gfp**2, rfp**2, gfp * rfp]), 12
    )[:, 36:-36, 36:-36]
    variance = moments[2:4] - moments[:2] ** 2
    valid = numpy.all(variance > 1e-6, axis=0)
    expected = numpy.zeros_like(gfp[36:-36, 36:-36])
    expected[valid] = (moments[4] - moments[0] * moments[1])[valid] / numpy.sqrt(
        variance[0][valid] * variance[1][valid]
    )
    numpy.testing.assert_array_equal(actual[:, :, 1], valid)
    numpy.testing.assert_allclose(actual[:, :, 0], expected, atol=2e-5)


def test_distance_field_matches_boundary_distances_and_profiles() -> None:
    device = get_shared().device
    channels = numpy.zeros((3, 19, 37), dtype=numpy.float32)
    channels[1, 3:16, 4:18] = 1
    channels[2, 3:16, 18:33] = 1
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result, profiles = compute.distance_field(source, (37, 19), 0.7, minimum_signal=0.3)
    actual = numpy.frombuffer(
        device.queue.read_buffer(result), dtype=numpy.float32
    ).reshape(19, 37, 2)
    smoothed = gaussian_reference(channels, 0.7)
    occupied = smoothed[1] + smoothed[2] >= 0.3
    padded_occupied = numpy.pad(occupied, 1)
    boundary = numpy.zeros_like(occupied)
    for offset_y, offset_x in ((0, 1), (2, 1), (1, 0), (1, 2)):
        neighbor = padded_occupied[offset_y : offset_y + 19, offset_x : offset_x + 37]
        boundary |= occupied & ~neighbor
    coordinates = numpy.moveaxis(numpy.indices((19, 37)), 0, -1)
    displacement = coordinates[:, :, None, :] - numpy.argwhere(boundary)
    expected = numpy.sqrt((displacement**2).sum(axis=3).min(axis=2))
    numpy.testing.assert_array_equal(actual[:, :, 1], occupied)
    numpy.testing.assert_allclose(
        actual[:, :, 0][occupied], expected[occupied], atol=1e-5
    )
    numpy.testing.assert_array_equal(actual[:, :, 0][~occupied], 0)
    actual_profiles = numpy.frombuffer(
        device.queue.read_buffer(profiles), dtype=numpy.float32
    ).reshape(10, 4)
    counts, edges = numpy.histogram(expected[occupied], bins=numpy.arange(11))
    numpy.testing.assert_array_equal(actual_profiles[:, 2], counts)
    numpy.testing.assert_array_equal(actual_profiles[:, 3], numpy.arange(10) + 0.5)
    for channel in (1, 2):
        sums, _ = numpy.histogram(
            expected[occupied], bins=edges, weights=channels[channel][occupied]
        )
        numpy.testing.assert_allclose(
            actual_profiles[:, channel - 1], sums / numpy.maximum(counts, 1), atol=1e-6
        )


@pytest.mark.parametrize("center", [(18.2, 9.3), (1.2, 2.3)], ids=["interior", "edge"])
def test_polar_sampling_and_profiles(center: tuple[float, float]) -> None:
    device = get_shared().device
    coordinates_y, coordinates_x = numpy.indices((19, 37), dtype=numpy.float32)
    channels = numpy.array(
        [numpy.full((19, 37), 0.25), coordinates_x / 37, coordinates_y / 19],
        dtype=numpy.float32,
    )
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result, profiles = compute.unwrap(source, (37, 19), center, 21.0)
    actual = numpy.frombuffer(
        device.queue.read_buffer(result), dtype=numpy.float32
    ).reshape(3, 19, 37)
    actual_profiles = numpy.frombuffer(
        device.queue.read_buffer(profiles), dtype=numpy.float32
    ).reshape(19, 4)
    angle = numpy.arange(37, dtype=numpy.float64) * (2 * numpy.pi / 37)
    radius = numpy.linspace(0, 21, 19)[:, None]
    sample_x = center[0] + radius * numpy.cos(angle)
    sample_y = center[1] + radius * numpy.sin(angle)
    inside = (sample_x >= 0) & (sample_x <= 36) & (sample_y >= 0) & (sample_y <= 18)
    expected = numpy.array([numpy.full((19, 37), 0.25), sample_x / 37, sample_y / 19])
    expected[:, ~inside] = 0
    numpy.testing.assert_allclose(actual, expected, atol=2e-6)
    expected_profiles = expected[1:].sum(axis=2).T / numpy.maximum(
        inside.sum(axis=1, keepdims=True), 1
    )
    numpy.testing.assert_allclose(actual_profiles[:, :2], expected_profiles, atol=2e-6)
    numpy.testing.assert_array_equal(actual_profiles[:, 2], inside.sum(axis=1))
    numpy.testing.assert_allclose(actual_profiles[:, 3], radius[:, 0], atol=2e-6)
