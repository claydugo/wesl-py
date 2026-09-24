from pathlib import Path

import imageio.v3 as imageio
import numpy
import pygfx
import wesl
import wgpu
from pygfx.renderers.wgpu import get_shared
from pygfx.utils.compute import ComputeShader


def load_colony() -> tuple[numpy.ndarray, numpy.ndarray, list[str]]:
    with imageio.imopen(
        "imageio:bacterial_colony.tif", "r", plugin="tifffile"
    ) as image_file:
        channels = image_file.read(index=0)
        metadata = image_file.metadata()
    colors = numpy.ones((3, 256, 4), dtype=numpy.float32)
    colors[:, :, :3] = numpy.asarray(metadata["LUTs"]).transpose(0, 2, 1) / 255
    return channels.astype(numpy.float32) / 255, colors, metadata["Labels"]


def composite(
    channels: wgpu.GPUBuffer,
    colors: numpy.ndarray,
    weights: numpy.ndarray,
    dimensions: tuple[int, int],
) -> tuple[pygfx.Texture, ComputeShader, wgpu.GPUBuffer]:
    device = get_shared().device
    width, height = dimensions
    directory = Path(__file__).parents[1]
    shader = ComputeShader(
        wesl.compile_file(
            directory / "imaging/composite.wesl", root_directory=directory
        ).wgsl,
        entry_point="main",
    )
    output = pygfx.Texture(
        dim=2,
        size=(width, height, 1),
        format="rgba8unorm",
        usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.TEXTURE_BINDING,
    )
    parameters = device.create_buffer_with_data(
        data=weights, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
    )
    shader.set_resource(0, channels)
    shader.set_resource(
        1, device.create_buffer_with_data(data=colors, usage=wgpu.BufferUsage.STORAGE)
    )
    shader.set_resource(2, output)
    shader.set_resource(3, parameters)
    shader.dispatch((width + 15) // 16, (height + 15) // 16)
    return output, shader, parameters
