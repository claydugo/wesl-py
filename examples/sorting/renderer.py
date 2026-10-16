from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import numpy as np
import wesl
import wgpu
from numpy.typing import NDArray
from rendercanvas import BaseRenderCanvas
from wgpu.utils import get_default_device


@dataclass
class Sort:
    title: str
    filename: str
    workgroup_count: int
    schedule: list[list[int]]
    values: wgpu.GPUBuffer
    marks: wgpu.GPUBuffer
    stage_uniform: wgpu.GPUBuffer
    scratch: wgpu.GPUBuffer | None = None
    stage: int = 0
    compute_bindings: wgpu.GPUBindGroup | None = None
    draw_bindings: wgpu.GPUBindGroup | None = None

    @property
    def finished(self) -> bool:
        return self.stage == len(self.schedule)


class Renderer:
    def __init__(self, canvas: BaseRenderCanvas) -> None:
        self.device = get_default_device()
        self.context = canvas.get_wgpu_context()
        self.format = self.context.get_preferred_format(self.device.adapter)
        self.context.configure(device=self.device, format=self.format)
        self.keys = sorted((Path(__file__).parent / "keys").glob("*.wesl"))
        self.compute_pipelines = {}
        self.bar_pipelines = {}
        project = wesl.Compiler.from_project(
            Path(__file__).parent, options=wesl.CompileOptions(visibility=True)
        )
        for key in self.keys:
            compiler = replace(
                project,
                modules={"package::examples::sorting::key": key.read_text()},
                filenames={"package::examples::sorting::key": key},
            )
            for filename in ("bitonic.wesl", "transposition.wesl", "radix.wesl"):
                module = self.device.create_shader_module(
                    code=compiler.compile_file(
                        f"examples/sorting/shaders/{filename}"
                    ).wgsl
                )
                self.compute_pipelines[key, filename] = (
                    self.device.create_compute_pipeline(
                        layout="auto",
                        compute={"module": module, "entry_point": "main"},
                    )
                )
            module = self.device.create_shader_module(
                code=compiler.compile_file("examples/sorting/shaders/bars.wesl").wgsl
            )
            self.bar_pipelines[key] = self.device.create_render_pipeline(
                layout="auto",
                vertex={"module": module, "entry_point": "vertex_main"},
                fragment={
                    "module": module,
                    "entry_point": "fragment_main",
                    "targets": [{"format": self.format}],
                },
            )
        self.display = self.create_uniform()
        self.key = self.keys[0]
        self.count = 0
        self.sorts: list[Sort] = []

    def create_storage(self) -> wgpu.GPUBuffer:
        return self.device.create_buffer(
            size=self.count * 4,
            usage=wgpu.BufferUsage.STORAGE
            | wgpu.BufferUsage.COPY_SRC
            | wgpu.BufferUsage.COPY_DST,
        )

    def create_uniform(self) -> wgpu.GPUBuffer:
        return self.device.create_buffer(
            size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )

    def upload(self, values: NDArray[np.uint32]) -> None:
        if len(values) != self.count:
            self.allocate(len(values))
        encoder = self.device.create_command_encoder()
        for sort in self.sorts:
            sort.stage = 0
            self.device.queue.write_buffer(sort.values, 0, values)
            encoder.clear_buffer(sort.marks)
        self.device.queue.submit([encoder.finish()])

    def allocate(self, count: int) -> None:
        for sort in self.sorts:
            for buffer in (sort.values, sort.marks, sort.stage_uniform, sort.scratch):
                if buffer is not None:
                    buffer.destroy()
        self.count = count
        self.sorts = [
            Sort(
                "Bitonic sort",
                "bitonic.wesl",
                (self.count + 63) // 64,
                [
                    [2**block, 2**distance]
                    for block in range(1, self.count.bit_length())
                    for distance in range(block - 1, -1, -1)
                ],
                self.create_storage(),
                self.create_storage(),
                self.create_uniform(),
            ),
            Sort(
                "Odd-even transposition sort",
                "transposition.wesl",
                (self.count // 2 + 63) // 64,
                [[phase % 2] for phase in range(self.count)],
                self.create_storage(),
                self.create_storage(),
                self.create_uniform(),
            ),
            Sort(
                "Radix sort",
                "radix.wesl",
                1,
                [[bit] for bit in range(10)],
                self.create_storage(),
                self.create_storage(),
                self.create_uniform(),
                scratch=self.create_storage(),
            ),
        ]
        self.select_key(self.key)

    def select_key(self, key: Path) -> None:
        self.key = key
        for sort in self.sorts:
            resources = [sort.values, sort.marks, sort.stage_uniform]
            if sort.scratch is not None:
                resources = [sort.values, sort.scratch, sort.marks, sort.stage_uniform]
            sort.compute_bindings = self.device.create_bind_group(
                layout=self.compute_pipelines[key, sort.filename].get_bind_group_layout(
                    0
                ),
                entries=[
                    {"binding": binding, "resource": {"buffer": buffer}}
                    for binding, buffer in enumerate(resources)
                ],
            )
            sort.draw_bindings = self.device.create_bind_group(
                layout=self.bar_pipelines[key].get_bind_group_layout(0),
                entries=[
                    {"binding": binding, "resource": {"buffer": buffer}}
                    for binding, buffer in enumerate(
                        [sort.values, sort.marks, self.display]
                    )
                ],
            )

    def advance(self, sort: Sort, encoder: wgpu.GPUCommandEncoder) -> None:
        encoder.clear_buffer(sort.marks)
        if sort.finished:
            return
        self.device.queue.write_buffer(
            sort.stage_uniform, 0, np.array(sort.schedule[sort.stage], dtype=np.uint32)
        )
        sort.stage += 1
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.compute_pipelines[self.key, sort.filename])
        compute_pass.set_bind_group(0, sort.compute_bindings)
        compute_pass.dispatch_workgroups(sort.workgroup_count)
        compute_pass.end()
        if sort.scratch is not None:
            encoder.copy_buffer_to_buffer(
                sort.scratch, 0, sort.values, 0, self.count * 4
            )

    def step(self) -> None:
        encoder = self.device.create_command_encoder()
        for sort in self.sorts:
            self.advance(sort, encoder)
        self.device.queue.submit([encoder.finish()])

    def presort(self, values: NDArray[np.uint32]) -> NDArray[np.uint32]:
        self.upload(values)
        radix = self.sorts[2]
        while not radix.finished:
            encoder = self.device.create_command_encoder()
            self.advance(radix, encoder)
            self.device.queue.submit([encoder.finish()])
        return self.read(radix)

    def read(self, sort: Sort) -> NDArray[np.uint32]:
        return np.frombuffer(
            self.device.queue.read_buffer(sort.values), dtype=np.uint32
        ).copy()

    def draw(
        self, viewports: list[tuple[float, float, float, float]], *, dots: bool
    ) -> None:
        target = cast("wgpu.GPUTexture", self.context.get_current_texture())
        encoder = self.device.create_command_encoder()
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": target.create_view(),
                    "resolve_target": None,
                    "load_op": "clear",
                    "store_op": "store",
                    "clear_value": (0.035, 0.05, 0.08, 1.0),
                }
            ]
        )
        if viewports:
            self.device.queue.write_buffer(
                self.display,
                0,
                np.array(viewports[0][2:], dtype=np.float32).tobytes()
                + np.array([dots, 0], dtype=np.uint32).tobytes(),
            )
            render_pass.set_pipeline(self.bar_pipelines[self.key])
            for sort, viewport in zip(self.sorts, viewports, strict=True):
                render_pass.set_viewport(*viewport, 0.0, 1.0)
                render_pass.set_bind_group(0, sort.draw_bindings)
                render_pass.draw(6, self.count)
        render_pass.end()
        self.device.queue.submit([encoder.finish()])
