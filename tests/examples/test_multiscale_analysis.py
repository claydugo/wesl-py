from importlib import import_module

import pytest

np = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")
pytest.importorskip("pygfx")
get_shared = import_module("pygfx.renderers.wgpu").get_shared
compute = import_module("examples.multiscale.compute")

pytestmark = pytest.mark.gpu


def gaussian_reference(fields: np.ndarray, sigma: float) -> np.ndarray:
    radius = int(np.ceil(3 * sigma))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    weights = np.exp(-0.5 * (offsets / sigma) ** 2)
    weights /= weights.sum()
    result = fields.astype(np.float64)
    for axis in (2, 1):
        padding = [(0, 0), (0, 0), (0, 0)]
        padding[axis] = (radius, radius)
        result = np.apply_along_axis(
            lambda values: np.convolve(values, weights, mode="valid"),
            axis,
            np.pad(result, padding, mode="edge"),
        )
    return result


def test_foreground_correlation() -> None:
    device = get_shared().device
    channels = np.full((3, 19, 37), 0.02, dtype=np.float32)
    channels[0] = 1
    channels[0, 3:16, 7:30] = 0.5
    channels[1, 3:16, 7:30] = np.linspace(0.2, 0.8, 23)
    channels[2, 3:16, 7:30] = 1 - channels[1, 3:16, 7:30]
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result = compute.analyze(source, (37, 19), 2.1)
    actual = np.frombuffer(device.queue.read_buffer(result), dtype=np.float32).reshape(
        19, 37, 2
    )
    gfp, rfp = channels[1:].astype(np.float64)
    foreground = channels[0] <= 0.9
    moments = gaussian_reference(
        np.array(
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
    moments[:5] /= np.maximum(moments[5], 1e-6)
    variance = moments[2:4] - moments[:2] ** 2
    expected = (moments[4] - moments[0] * moments[1])[foreground] / np.sqrt(
        variance[0][foreground] * variance[1][foreground]
    )
    np.testing.assert_allclose(actual[:, :, 0][foreground], expected, atol=1e-4)
    np.testing.assert_allclose(actual[:, :, 0][foreground], -1, atol=1e-4)
    np.testing.assert_array_equal(actual[:, :, 1], foreground)
    np.testing.assert_array_equal(actual[~foreground], 0)


def test_correlation_brightness_offsets() -> None:
    device = get_shared().device
    pattern = np.random.default_rng(917).random((2, 129, 129)) < 0.085
    pattern[1] = pattern[0]
    channels = np.full((3, 129, 129), 0.5, dtype=np.float32)
    channels[1:] = (227 + pattern.astype(np.float32)) / 255
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result = compute.analyze(source, (129, 129), 12)
    actual = np.frombuffer(device.queue.read_buffer(result), dtype=np.float32).reshape(
        129, 129, 2
    )[36:-36, 36:-36]
    gfp, rfp = channels[1:].astype(np.float64)
    moments = gaussian_reference(np.array([gfp, rfp, gfp**2, rfp**2, gfp * rfp]), 12)[
        :, 36:-36, 36:-36
    ]
    variance = moments[2:4] - moments[:2] ** 2
    valid = np.all(variance > 1e-6, axis=0)
    expected = np.zeros_like(gfp[36:-36, 36:-36])
    expected[valid] = (moments[4] - moments[0] * moments[1])[valid] / np.sqrt(
        variance[0][valid] * variance[1][valid]
    )
    np.testing.assert_array_equal(actual[:, :, 1], valid)
    np.testing.assert_allclose(actual[:, :, 0], expected, atol=2e-5)


def test_distance_field_matches_boundary_distances_and_profiles() -> None:
    device = get_shared().device
    channels = np.zeros((3, 19, 37), dtype=np.float32)
    channels[1, 3:16, 4:18] = 1
    channels[2, 3:16, 18:33] = 1
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result, profiles = compute.distance_field(source, (37, 19), 0.7, minimum_signal=0.3)
    actual = np.frombuffer(device.queue.read_buffer(result), dtype=np.float32).reshape(
        19, 37, 2
    )
    smoothed = gaussian_reference(channels, 0.7)
    occupied = smoothed[1] + smoothed[2] >= 0.3
    padded_occupied = np.pad(occupied, 1)
    boundary = np.zeros_like(occupied)
    for offset_y, offset_x in ((0, 1), (2, 1), (1, 0), (1, 2)):
        neighbor = padded_occupied[offset_y : offset_y + 19, offset_x : offset_x + 37]
        boundary |= occupied & ~neighbor
    coordinates = np.moveaxis(np.indices((19, 37)), 0, -1)
    displacement = coordinates[:, :, None, :] - np.argwhere(boundary)
    expected = np.sqrt((displacement**2).sum(axis=3).min(axis=2))
    np.testing.assert_array_equal(actual[:, :, 1], occupied)
    np.testing.assert_allclose(actual[:, :, 0][occupied], expected[occupied], atol=1e-5)
    np.testing.assert_array_equal(actual[:, :, 0][~occupied], 0)
    actual_profiles = np.frombuffer(
        device.queue.read_buffer(profiles), dtype=np.float32
    ).reshape(10, 4)
    counts, edges = np.histogram(expected[occupied], bins=np.arange(11))
    np.testing.assert_array_equal(actual_profiles[:, 2], counts)
    np.testing.assert_array_equal(actual_profiles[:, 3], np.arange(10) + 0.5)
    for channel in (1, 2):
        sums, _ = np.histogram(
            expected[occupied], bins=edges, weights=channels[channel][occupied]
        )
        np.testing.assert_allclose(
            actual_profiles[:, channel - 1], sums / np.maximum(counts, 1), atol=1e-6
        )


@pytest.mark.parametrize("center", [(18.2, 9.3), (1.2, 2.3)], ids=["interior", "edge"])
def test_polar_sampling_and_profiles(center: tuple[float, float]) -> None:
    device = get_shared().device
    coordinates_y, coordinates_x = np.indices((19, 37), dtype=np.float32)
    channels = np.array(
        [np.full((19, 37), 0.25), coordinates_x / 37, coordinates_y / 19],
        dtype=np.float32,
    )
    source = device.create_buffer_with_data(
        data=channels, usage=wgpu.BufferUsage.STORAGE
    )
    result, profiles = compute.unwrap(source, (37, 19), center, 21.0)
    actual = np.frombuffer(device.queue.read_buffer(result), dtype=np.float32).reshape(
        3, 19, 37
    )
    actual_profiles = np.frombuffer(
        device.queue.read_buffer(profiles), dtype=np.float32
    ).reshape(19, 4)
    angle = np.arange(37, dtype=np.float64) * (2 * np.pi / 37)
    radius = np.linspace(0, 21, 19)[:, None]
    sample_x = center[0] + radius * np.cos(angle)
    sample_y = center[1] + radius * np.sin(angle)
    inside = (sample_x >= 0) & (sample_x <= 36) & (sample_y >= 0) & (sample_y <= 18)
    expected = np.array([np.full((19, 37), 0.25), sample_x / 37, sample_y / 19])
    expected[:, ~inside] = 0
    np.testing.assert_allclose(actual, expected, atol=2e-6)
    expected_profiles = expected[1:].sum(axis=2).T / np.maximum(
        inside.sum(axis=1, keepdims=True), 1
    )
    np.testing.assert_allclose(actual_profiles[:, :2], expected_profiles, atol=2e-6)
    np.testing.assert_array_equal(actual_profiles[:, 2], inside.sum(axis=1))
    np.testing.assert_allclose(actual_profiles[:, 3], radius[:, 0], atol=2e-6)
