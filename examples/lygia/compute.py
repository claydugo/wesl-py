from pathlib import Path

import numpy
import wesl
import wgpu
from numpy.typing import NDArray


def colorize(
    device: wgpu.GPUDevice,
    values: NDArray[numpy.float32],
    *,
    library_directory: Path,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> NDArray[numpy.float32]:
    try:
        height, width = values.shape
    except ValueError:
        message = "values must be a nonempty image"
        raise ValueError(message) from None
    if height == 0 or width == 0:
        message = "values must be a nonempty image"
        raise ValueError(message)
    with numpy.errstate(over="ignore", invalid="ignore"):
        limits = numpy.asarray([minimum, maximum], dtype=numpy.float32)
        span = limits[1] - limits[0]
    if not numpy.isfinite(limits).all() or not numpy.isfinite(span) or span <= 0:
        message = "display limits must have a finite positive f32 range"
        raise ValueError(message)
    directory = Path(__file__).parent
    shader = wesl.compile_file(
        directory / "image.wesl",
        root_directory=directory.parent,
        dependencies={"lygia": library_directory},
    )
    pipeline = device.create_compute_pipeline(
        layout="auto",
        compute={
            "module": device.create_shader_module(code=shader.wgsl),
            "entry_point": "main",
            "constants": {"minimum": minimum, "maximum": maximum, "width": width},
        },
    )
    buffers = []
    try:
        source = device.create_buffer_with_data(
            data=numpy.ascontiguousarray(values, dtype=numpy.float32),
            usage=wgpu.BufferUsage.STORAGE,
        )
        buffers.append(source)
        output = device.create_buffer(
            size=values.size * 16,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        buffers.append(output)
        bindings = device.create_bind_group(
            layout=pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": 0, "resource": {"buffer": source}},
                {"binding": 1, "resource": {"buffer": output}},
            ],
        )
        encoder = device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        compute_pass.set_bind_group(0, bindings)
        compute_pass.dispatch_workgroups((width + 7) // 8, (height + 7) // 8)
        compute_pass.end()
        device.queue.submit([encoder.finish()])
        return numpy.frombuffer(
            device.queue.read_buffer(output), dtype=numpy.float32
        ).reshape(height, width, 4)
    finally:
        for buffer in buffers:
            buffer.destroy()
