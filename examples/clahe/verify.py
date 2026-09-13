import argparse

import numpy
from pygfx.renderers.wgpu import get_shared

from examples.clahe.compute import equalize
from examples.common import load_colony

parser = argparse.ArgumentParser(description="Verify CLAHE shaders against NumPy.")
parser.add_argument("--image", action="store_true", help="Also verify the full TIFF.")
arguments = parser.parse_args()
device = get_shared().device
random = numpy.random.default_rng(42)
cases = [
    numpy.array([0, 127, 255], dtype=numpy.uint8).reshape(3, 1, 1),
    numpy.stack(
        [
            numpy.zeros((19, 37), dtype=numpy.uint8),
            numpy.full((19, 37), 255, dtype=numpy.uint8),
            numpy.arange(19 * 37, dtype=numpy.uint16)
            .reshape(19, 37)
            .astype(numpy.uint8),
        ]
    ),
    random.integers(0, 256, (3, 67, 71), dtype=numpy.uint8),
]
if arguments.image:
    channels, _, _ = load_colony()
    cases.append(numpy.rint(channels * 255).astype(numpy.uint8))

for image in cases:
    channel_count, height, width = image.shape
    for tile_size, clip_limit in ((16, 0.5), (31, 1.75), (64, 5.5), (128, 2.0)):
        tile_rows = (height + tile_size - 1) // tile_size
        tile_columns = (width + tile_size - 1) // tile_size
        padded = numpy.pad(
            image,
            (
                (0, 0),
                (0, tile_rows * tile_size - height),
                (0, tile_columns * tile_size - width),
            ),
            mode="edge",
        )
        tiles = (
            padded.reshape(channel_count, tile_rows, tile_size, tile_columns, tile_size)
            .transpose(0, 1, 3, 2, 4)
            .reshape(-1, tile_size * tile_size)
        )
        expected_histograms = numpy.apply_along_axis(
            lambda values: numpy.bincount(values, minlength=256), 1, tiles
        )
        limit = max(1, int(clip_limit * tile_size * tile_size / 256))
        clipped = numpy.minimum(expected_histograms, limit)
        excess = (expected_histograms - clipped).sum(axis=1)
        clipped += excess[:, None] // 256
        for histogram, remainder in zip(clipped, excess % 256, strict=True):
            if remainder:
                histogram[numpy.arange(remainder) * (256 // remainder)] += 1
        expected_tables = clipped.cumsum(axis=1) / (tile_size * tile_size)
        tables = expected_tables.reshape(channel_count, tile_rows, tile_columns, 256)
        horizontal = numpy.arange(width) / tile_size - 0.5
        vertical = numpy.arange(height) / tile_size - 0.5
        lower_x = numpy.floor(horizontal).astype(numpy.int32)
        lower_y = numpy.floor(vertical).astype(numpy.int32)
        fraction_x = (horizontal - lower_x)[None, None, :]
        fraction_y = (vertical - lower_y)[None, :, None]
        channel_indices = numpy.arange(channel_count)[:, None, None]
        corners = []
        for offset_y, offset_x in ((0, 0), (0, 1), (1, 0), (1, 1)):
            rows = numpy.clip(lower_y + offset_y, 0, tile_rows - 1)
            columns = numpy.clip(lower_x + offset_x, 0, tile_columns - 1)
            corners.append(
                tables[
                    channel_indices, rows[None, :, None], columns[None, None, :], image
                ]
            )
        top = corners[0] * (1 - fraction_x) + corners[1] * fraction_x
        bottom = corners[2] * (1 - fraction_x) + corners[3] * fraction_x
        expected = top * (1 - fraction_y) + bottom * fraction_y
        source, histograms, lookup_tables, output = equalize(
            device, image.astype(numpy.float32) / 255, tile_size, clip_limit
        )
        actual_histograms = numpy.frombuffer(
            device.queue.read_buffer(histograms), dtype=numpy.uint32
        ).reshape(expected_histograms.shape)
        numpy.testing.assert_array_equal(actual_histograms, expected_histograms)
        actual_tables = numpy.frombuffer(
            device.queue.read_buffer(lookup_tables), dtype=numpy.float32
        ).reshape(expected_tables.shape)
        numpy.testing.assert_allclose(actual_tables, expected_tables, rtol=0, atol=1e-7)
        actual = numpy.frombuffer(
            device.queue.read_buffer(output), dtype=numpy.float32
        ).reshape(image.shape)
        numpy.testing.assert_allclose(actual, expected, rtol=0, atol=3e-7)
        print(
            f"Verified CLAHE: shape={image.shape}, "
            f"tile_size={tile_size}, clip_limit={clip_limit}"
        )
