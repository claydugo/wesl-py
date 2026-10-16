from math import isfinite
from pathlib import Path

import numpy as np
import wesl
import wgpu
from numpy.typing import NDArray


class RMSNorm:
    def __init__(
        self,
        device: wgpu.GPUDevice,
        column_count: int,
        *,
        residual: bool = False,
        epsilon: float = 1e-6,
    ) -> None:
        if not isfinite(epsilon) or epsilon < 2**-126:
            message = "epsilon must be finite and at least the smallest normal f32"
            raise ValueError(message)
        directory = Path(__file__).parent
        shader = wesl.compile_file(
            directory / "shaders/normalize.wesl",
            root_directory=directory.parent.parent,
            options=wesl.CompileOptions(
                visibility=True,
                features=wesl.Features(flags={"residual": residual}),
            ),
        )
        self.pipeline = device.create_compute_pipeline(
            layout="auto",
            compute={
                "module": device.create_shader_module(code=shader.wgsl),
                "entry_point": "main",
                "constants": {"0": column_count, "1": epsilon},
            },
        )
        self.device = device
        self.column_count = column_count
        self.residual_enabled = residual

    def normalize(
        self,
        values: NDArray[np.float32],
        weights: NDArray[np.float32],
        *,
        residual: NDArray[np.float32] | None = None,
    ) -> NDArray[np.float32]:
        if (
            values.ndim != 2
            or weights.ndim != 1
            or values.size == 0
            or values.shape[1] != weights.size
            or weights.size != self.column_count
        ):
            message = "values must be a nonempty matrix with one weight per column"
            raise ValueError(message)
        if residual is not None and residual.shape != values.shape:
            message = "residual must have the same shape as values"
            raise ValueError(message)
        if (residual is not None) != self.residual_enabled:
            message = "residual presence must match the prepared pipeline"
            raise ValueError(message)
        buffers = []
        try:
            entries = []
            for binding, data in ((0, values), (1, residual), (2, weights)):
                if data is not None:
                    buffer = self.device.create_buffer_with_data(
                        data=np.ascontiguousarray(data, dtype=np.float32),
                        usage=wgpu.BufferUsage.STORAGE,
                    )
                    buffers.append(buffer)
                    entries.append({"binding": binding, "resource": {"buffer": buffer}})
            output = self.device.create_buffer(
                size=values.size * 4,
                usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
            )
            buffers.append(output)
            entries.append({"binding": 3, "resource": {"buffer": output}})
            bindings = self.device.create_bind_group(
                layout=self.pipeline.get_bind_group_layout(0), entries=entries
            )
            encoder = self.device.create_command_encoder()
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.pipeline)
            compute_pass.set_bind_group(0, bindings)
            compute_pass.dispatch_workgroups(values.shape[0])
            compute_pass.end()
            self.device.queue.submit([encoder.finish()])
            return np.frombuffer(
                self.device.queue.read_buffer(output), dtype=np.float32
            ).reshape(values.shape)
        finally:
            for buffer in buffers:
                buffer.destroy()
