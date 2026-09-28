from math import isfinite
from pathlib import Path

import numpy
import wesl
import wgpu
from numpy.typing import NDArray


def normalize(
    device: wgpu.GPUDevice,
    values: NDArray[numpy.float32],
    weights: NDArray[numpy.float32],
    *,
    residual: NDArray[numpy.float32] | None = None,
    epsilon: float = 1e-6,
) -> NDArray[numpy.float32]:
    if (
        values.ndim != 2  # noqa: PLR2004
        or weights.ndim != 1
        or values.size == 0
        or values.shape[1] != weights.size
    ):
        message = "values must be a nonempty matrix with one weight per column"
        raise ValueError(message)
    if residual is not None and residual.shape != values.shape:
        message = "residual must have the same shape as values"
        raise ValueError(message)
    if not isfinite(epsilon) or epsilon < 2**-126:
        message = "epsilon must be finite and at least the smallest normal f32"
        raise ValueError(message)
    directory = Path(__file__).parent
    shader = wesl.compile_file(
        directory / "shaders/normalize.wesl",
        root_directory=directory.parent.parent,
        options=wesl.CompileOptions(
            visibility=True,
            features=wesl.Features(flags={"residual": residual is not None}),
        ),
    )
    pipeline = device.create_compute_pipeline(
        layout="auto",
        compute={
            "module": device.create_shader_module(code=shader.wgsl),
            "entry_point": "main",
            "constants": {"0": weights.size, "1": epsilon},
        },
    )
    buffers = []
    try:
        entries = []
        for binding, data in ((0, values), (1, residual), (2, weights)):
            if data is not None:
                buffer = device.create_buffer_with_data(
                    data=numpy.ascontiguousarray(data, dtype=numpy.float32),
                    usage=wgpu.BufferUsage.STORAGE,
                )
                buffers.append(buffer)
                entries.append({"binding": binding, "resource": {"buffer": buffer}})
        output = device.create_buffer(
            size=values.size * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        buffers.append(output)
        entries.append({"binding": 3, "resource": {"buffer": output}})
        bindings = device.create_bind_group(
            layout=pipeline.get_bind_group_layout(0), entries=entries
        )
        encoder = device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        compute_pass.set_bind_group(0, bindings)
        compute_pass.dispatch_workgroups(values.shape[0])
        compute_pass.end()
        device.queue.submit([encoder.finish()])
        return numpy.frombuffer(
            device.queue.read_buffer(output), dtype=numpy.float32
        ).reshape(values.shape)
    finally:
        for buffer in buffers:
            buffer.destroy()
