from pathlib import Path

import numpy
import wesl
import wgpu
from pygfx.utils.compute import ComputeShader


def equalize(
    device: wgpu.GPUDevice,
    channels: numpy.ndarray,
    tile_size: int,
    clip_limit: float,
) -> tuple[wgpu.GPUBuffer, wgpu.GPUBuffer, wgpu.GPUBuffer, wgpu.GPUBuffer]:
    directory = Path(__file__).parent
    channel_count, height, width = channels.shape
    tile_columns = (width + tile_size - 1) // tile_size
    tile_rows = (height + tile_size - 1) // tile_size
    source = device.create_buffer_with_data(
        data=numpy.ascontiguousarray(channels, dtype=numpy.float32),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    histograms, lookup_tables = (
        device.create_buffer(
            size=channel_count * tile_rows * tile_columns * 256 * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        for _ in range(2)
    )
    output = device.create_buffer(
        size=channels.size * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    histogram = ComputeShader(
        wesl.compile_file(
            directory / "histogram.wesl", root_directory=directory.parent
        ).wgsl,
        entry_point="main",
    )
    histogram.set_resource(0, source)
    histogram.set_resource(1, histograms)
    histogram.set_constant("width", width)
    histogram.set_constant("height", height)
    histogram.set_constant("tile_size", tile_size)
    histogram.dispatch(tile_columns, tile_rows, channel_count)
    equalization = ComputeShader(
        wesl.compile_file(directory / "equalize.wesl").wgsl, entry_point="main"
    )
    equalization.set_resource(0, histograms)
    equalization.set_resource(1, lookup_tables)
    equalization.set_constant("tile_size", tile_size)
    equalization.set_constant("clip_limit", clip_limit)
    equalization.dispatch(channel_count * tile_columns * tile_rows)
    interpolation = ComputeShader(
        wesl.compile_file(
            directory / "apply.wesl", root_directory=directory.parent
        ).wgsl,
        entry_point="main",
    )
    interpolation.set_resource(0, source)
    interpolation.set_resource(1, lookup_tables)
    interpolation.set_resource(2, output)
    interpolation.set_constant("width", width)
    interpolation.set_constant("height", height)
    interpolation.set_constant("tile_size", tile_size)
    interpolation.dispatch((width + 15) // 16, (height + 15) // 16, channel_count)
    return source, histograms, lookup_tables, output
