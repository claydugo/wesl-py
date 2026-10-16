from contextlib import ExitStack
from pathlib import Path

import numpy as np
import wesl
import wgpu
from numpy.typing import NDArray


class Compactor:
    def __init__(
        self,
        device: wgpu.GPUDevice,
        *,
        threshold: int = 500,
        keep_below: bool = False,
    ) -> None:
        directory = Path(__file__).parent
        self.pipelines = {}
        for name, filename, select_values, constants in (
            ("select", "shaders/scan.wesl", True, {"0": threshold}),
            ("scan", "shaders/scan.wesl", False, {}),
            ("offsets", "shaders/offsets.wesl", False, {}),
            ("scatter", "shaders/scatter.wesl", False, {"0": threshold}),
        ):
            shader = wesl.compile_file(
                directory / filename,
                root_directory=directory.parent.parent,
                options=wesl.CompileOptions(
                    visibility=True,
                    features=wesl.Features(
                        flags={"select_values": select_values, "keep_below": keep_below}
                    ),
                ),
            )
            self.pipelines[name] = device.create_compute_pipeline(
                layout="auto",
                compute={
                    "module": device.create_shader_module(code=shader.wgsl),
                    "entry_point": "main",
                    "constants": constants,
                },
            )

        self.device = device

    def compact(self, values: NDArray[np.uint32]) -> NDArray[np.uint32]:
        if values.ndim != 1 or values.dtype != np.uint32:
            message = "values must be a one-dimensional uint32 array"
            raise ValueError(message)
        if values.size == 0:
            return np.empty(0, dtype=np.uint32)

        def allocate(size: int) -> wgpu.GPUBuffer:
            buffer = self.device.create_buffer(
                size=size,
                usage=wgpu.BufferUsage.STORAGE
                | wgpu.BufferUsage.COPY_SRC
                | wgpu.BufferUsage.COPY_DST,
            )
            stack.callback(buffer.destroy)
            return buffer

        encoder = self.device.create_command_encoder()

        def dispatch(name: str, resources: list[wgpu.GPUBuffer], count: int) -> None:
            pipeline = self.pipelines[name]
            bindings = self.device.create_bind_group(
                layout=pipeline.get_bind_group_layout(0),
                entries=[
                    {"binding": binding, "resource": {"buffer": buffer}}
                    for binding, buffer in enumerate(resources)
                ],
            )
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(pipeline)
            compute_pass.set_bind_group(0, bindings)
            compute_pass.dispatch_workgroups(count)
            compute_pass.end()

        with ExitStack() as stack:
            source = allocate(len(values) * 4)
            self.device.queue.write_buffer(source, 0, np.ascontiguousarray(values))
            levels = []
            current = source
            count = len(values)
            while True:
                group_count = (count + 127) // 128
                prefixes = allocate(count * 4)
                totals = allocate(group_count * 4)
                dispatch(
                    "select" if not levels else "scan",
                    [current, prefixes, totals],
                    group_count,
                )
                levels.append(prefixes)
                if group_count == 1:
                    break
                current = totals
                count = group_count
            for index in range(len(levels) - 2, -1, -1):
                dispatch(
                    "offsets",
                    [levels[index], levels[index + 1]],
                    (levels[index].size // 4 + 127) // 128,
                )
            output = allocate(len(values) * 4)
            dispatch("scatter", [source, levels[0], output], (len(values) + 127) // 128)
            self.device.queue.submit([encoder.finish()])
            selected_count = self.device.queue.read_buffer(totals).cast("I")[0]
            if not selected_count:
                return np.empty(0, dtype=np.uint32)
            return np.frombuffer(
                self.device.queue.read_buffer(output, size=selected_count * 4),
                dtype=np.uint32,
            )
