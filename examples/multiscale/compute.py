from pathlib import Path

import numpy
import wesl
import wgpu
from pygfx.renderers.wgpu import get_shared
from pygfx.utils.compute import ComputeShader


def create_shader(
    filename: str,
    dimensions: tuple[int, int] | None = None,
    *,
    entry_point: str = "main",
    **features: bool,
) -> ComputeShader:
    directory = Path(__file__).parent
    result = wesl.compile_file(
        directory / "shaders" / filename,
        root_directory=directory.parent,
        options=wesl.CompileOptions(
            keep=[entry_point], features=wesl.Features(flags=dict(features))
        ),
    )
    shader = ComputeShader(result.wgsl, entry_point=entry_point)
    if dimensions is not None:
        shader.set_constant("width", dimensions[0])
        shader.set_constant("height", dimensions[1])
    return shader


def smooth(
    source: wgpu.GPUBuffer,
    shape: tuple[int, int, int],
    sigma: float,
    *,
    first_field: int = 0,
) -> wgpu.GPUBuffer:
    device = get_shared().device
    field_count, height, width = shape
    intermediate, output = (
        device.create_buffer(
            size=field_count * height * width * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        for _ in range(2)
    )
    radius = int(numpy.ceil(3 * sigma))
    offsets = numpy.arange(-radius, radius + 1, dtype=numpy.float64)
    coefficients = numpy.exp(-0.5 * (offsets / sigma) ** 2)
    coefficients = (coefficients / coefficients.sum()).astype(numpy.float32)
    weights = device.create_buffer_with_data(
        data=coefficients, usage=wgpu.BufferUsage.STORAGE
    )
    for horizontal, input_buffer, output_buffer in (
        (True, source, intermediate),
        (False, intermediate, output),
    ):
        shader = create_shader("filter.wesl", (width, height), horizontal=horizontal)
        shader.set_resource(0, input_buffer)
        shader.set_resource(1, output_buffer)
        shader.set_resource(2, weights)
        shader.set_constant("0", radius)
        shader.set_constant("first_field", first_field)
        if horizontal:
            shader.dispatch((width + 63) // 64, height, field_count - first_field)
        else:
            shader.dispatch((height + 63) // 64, width, field_count - first_field)
    return output


def enhance(
    channels: numpy.ndarray,
    sigma: float,
    strength: float,
) -> tuple[wgpu.GPUBuffer, wgpu.GPUBuffer, wgpu.GPUBuffer, wgpu.GPUBuffer]:
    device = get_shared().device
    source = device.create_buffer_with_data(
        data=numpy.ascontiguousarray(channels, dtype=numpy.float32),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    fine = smooth(source, channels.shape, sigma, first_field=1)
    coarse = smooth(source, channels.shape, sigma * 2, first_field=1)
    output = device.create_buffer(
        size=channels.size * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    shader = create_shader("enhancement.wesl")
    shader.set_resource(0, source)
    shader.set_resource(1, fine)
    shader.set_resource(2, coarse)
    shader.set_resource(3, output)
    shader.set_constant("strength", strength)
    shader.dispatch((channels.size + 255) // 256)
    return source, fine, coarse, output


def analyze(
    source: wgpu.GPUBuffer,
    dimensions: tuple[int, int],
    sigma: float,
    *,
    maximum_brightfield: float = 0.9,
) -> wgpu.GPUBuffer:
    device = get_shared().device
    width, height = dimensions
    intermediate = device.create_buffer(
        size=height * width * 32, usage=wgpu.BufferUsage.STORAGE
    )
    radius = int(numpy.ceil(3 * sigma))
    offsets = numpy.arange(-radius, radius + 1, dtype=numpy.float64)
    coefficients = numpy.exp(-0.5 * (offsets / sigma) ** 2)
    weights = device.create_buffer_with_data(
        data=(coefficients / coefficients.sum()).astype(numpy.float32),
        usage=wgpu.BufferUsage.STORAGE,
    )
    output = device.create_buffer(
        size=height * width * 8,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    for horizontal, destination in ((True, intermediate), (False, output)):
        shader = create_shader("correlation.wesl", dimensions, horizontal=horizontal)
        shader.set_resource(0, source)
        shader.set_resource(1, destination)
        shader.set_resource(2, weights)
        shader.set_constant("0", radius)
        shader.set_constant("maximum_brightfield", maximum_brightfield)
        if horizontal:
            shader.dispatch((width + 63) // 64, height)
        else:
            shader.set_resource(3, intermediate)
            shader.dispatch((height + 63) // 64, width)
    return output


def distance_field(
    source: wgpu.GPUBuffer,
    dimensions: tuple[int, int],
    sigma: float,
    *,
    minimum_signal: float = 0.06,
) -> tuple[wgpu.GPUBuffer, wgpu.GPUBuffer]:
    device = get_shared().device
    width, height = dimensions
    smoothed = smooth(source, (3, height, width), sigma, first_field=1)
    seeds, intermediate, output = (
        device.create_buffer(
            size=height * width * 8,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        for _ in range(3)
    )
    shader = create_shader("perimeter/seeds.wesl", dimensions)
    shader.set_resource(0, smoothed)
    shader.set_resource(1, seeds)
    shader.set_constant("minimum_signal", minimum_signal)
    shader.dispatch((width + 15) // 16, (height + 15) // 16)
    shader = create_shader("perimeter/jump.wesl", dimensions)
    step = (1 << (max(dimensions) - 1).bit_length()) // 2
    while step:
        shader.set_resource(0, seeds)
        shader.set_resource(1, intermediate)
        shader.set_constant("step", step)
        shader.dispatch((width + 15) // 16, (height + 15) // 16)
        seeds, intermediate = intermediate, seeds
        step //= 2
    shader = create_shader("perimeter/distance.wesl", dimensions)
    shader.set_resource(0, seeds)
    shader.set_resource(1, output)
    shader.set_resource(2, smoothed)
    shader.set_constant("minimum_signal", minimum_signal)
    shader.dispatch((width + 15) // 16, (height + 15) // 16)
    profile_count = min(64, (min(dimensions) + 1) // 2)
    chunk_count = (width * height + 16383) // 16384
    partials = device.create_buffer(
        size=chunk_count * profile_count * 16, usage=wgpu.BufferUsage.STORAGE
    )
    profiles = device.create_buffer(
        size=profile_count * 16,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    shader = create_shader(
        "profiles.wesl", dimensions, entry_point="accumulate_distance"
    )
    shader.set_resource(0, source)
    shader.set_resource(2, partials)
    shader.set_resource(3, output)
    shader.set_constant("profile_count", profile_count)
    shader.dispatch(profile_count, chunk_count)
    shader = create_shader("profiles.wesl", dimensions, entry_point="finalize_distance")
    shader.set_resource(1, profiles)
    shader.set_resource(2, partials)
    shader.set_constant("profile_count", profile_count)
    shader.dispatch(profile_count)
    return output, profiles


def unwrap(
    source: wgpu.GPUBuffer,
    dimensions: tuple[int, int],
    center: tuple[float, float],
    maximum_radius: float,
) -> tuple[wgpu.GPUBuffer, wgpu.GPUBuffer]:
    device = get_shared().device
    width, height = dimensions
    output = device.create_buffer(
        size=3 * height * width * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    profiles = device.create_buffer(
        size=height * 16,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    shader = create_shader("polar.wesl", dimensions)
    shader.set_resource(0, source)
    shader.set_resource(1, output)
    shader.set_constant("center_x", center[0])
    shader.set_constant("center_y", center[1])
    shader.set_constant("maximum_radius", maximum_radius)
    shader.dispatch((width + 15) // 16, (height + 15) // 16)
    shader = create_shader("profiles.wesl", dimensions, entry_point="radial_profile")
    shader.set_resource(0, output)
    shader.set_resource(1, profiles)
    shader.set_constant("center_x", center[0])
    shader.set_constant("center_y", center[1])
    shader.set_constant("maximum_radius", maximum_radius)
    shader.dispatch(height)
    return output, profiles
