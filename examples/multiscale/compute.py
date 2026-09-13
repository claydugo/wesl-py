from pathlib import Path

import numpy
import wesl
import wgpu
from pygfx.utils.compute import ComputeShader


def enhance(
    device: wgpu.GPUDevice,
    channels: numpy.ndarray,
    sigma: float,
    strength: float,
    *,
    tiled: bool = False,
) -> tuple[wgpu.GPUBuffer, wgpu.GPUBuffer, wgpu.GPUBuffer, wgpu.GPUBuffer]:
    directory = Path(__file__).parent
    _, height, width = channels.shape
    source = device.create_buffer_with_data(
        data=numpy.ascontiguousarray(channels, dtype=numpy.float32),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    intermediate = device.create_buffer(
        size=channels.size * 4, usage=wgpu.BufferUsage.STORAGE
    )
    fine, coarse, output = (
        device.create_buffer(
            size=channels.size * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        for _ in range(3)
    )
    for deviation, destination in ((sigma, fine), (sigma * 2, coarse)):
        radius = int(numpy.ceil(3 * deviation))
        offsets = numpy.arange(-radius, radius + 1, dtype=numpy.float64)
        coefficients = numpy.exp(-0.5 * (offsets / deviation) ** 2)
        coefficients = (coefficients / coefficients.sum()).astype(numpy.float32)
        weights = device.create_buffer_with_data(
            data=coefficients, usage=wgpu.BufferUsage.STORAGE
        )
        for horizontal, input_buffer, output_buffer in (
            (True, source, intermediate),
            (False, intermediate, destination),
        ):
            result = wesl.compile_file(
                directory / "filter.wesl",
                root_directory=directory.parent,
                features={"horizontal": horizontal, "tiled": tiled},
            )
            shader = ComputeShader(result.wgsl, entry_point="main")
            shader.set_resource(0, input_buffer)
            shader.set_resource(1, output_buffer)
            shader.set_resource(2, weights)
            shader.set_constant("0", radius)
            shader.set_constant("width", width)
            shader.set_constant("height", height)
            if horizontal:
                shader.dispatch((width + 63) // 64, height, 2)
            else:
                shader.dispatch((height + 63) // 64, width, 2)
    shader = ComputeShader(
        wesl.compile_file(directory / "enhancement.wesl").wgsl, entry_point="main"
    )
    shader.set_resource(0, source)
    shader.set_resource(1, fine)
    shader.set_resource(2, coarse)
    shader.set_resource(3, output)
    shader.set_constant("strength", strength)
    shader.dispatch((channels.size + 255) // 256)
    return source, fine, coarse, output
