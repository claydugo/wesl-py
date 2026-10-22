from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import numpy as np
import wesl
import wgpu
from numpy.typing import NDArray
from rendercanvas import BaseRenderCanvas
from wgpu.utils import get_default_device

from examples.optimizers.layout import create_layout


@dataclass
class Rule:
    title: str
    filename: str
    learning_rate: float
    constants: dict[str, float]


class Renderer:
    def __init__(self, canvas: BaseRenderCanvas, width: int) -> None:
        self.device = get_default_device()
        self.context = canvas.get_wgpu_context()
        self.format = self.context.get_preferred_format(self.device.adapter)
        self.context.configure(device=self.device, format=self.format)
        self.layout = create_layout(width)
        self.rules = [
            Rule("Gradient descent", "gradient_descent.wesl", 0.5, {}),
            Rule("Momentum", "momentum.wesl", 0.05, {"0": 0.9}),
            Rule("Adam", "adam.wesl", 0.01, {"0": 0.9, "1": 0.999}),
        ]
        self.learning_rates = [
            self.device.create_buffer(
                size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
            )
            for _ in self.rules
        ]
        self.progress = self.device.create_buffer(
            size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self.project = wesl.Compiler.from_project(
            Path(__file__).parent, options=wesl.CompileOptions(visibility=True)
        )
        self.modified = {}
        self.buffers = []
        self.build()

    def compile(self, filename: str, rule: Rule | None = None) -> wesl.CompileResult:
        compiler = self.project
        if rule is not None:
            path = Path(__file__).parent / "rules" / rule.filename
            compiler = replace(
                self.project,
                modules={"package::examples::optimizers::rule": path.read_text()},
                filenames={"package::examples::optimizers::rule": path},
            )
        return compiler.compile_file(
            f"examples/optimizers/shaders/{filename}",
            constants=self.layout,
        )

    def build(self) -> None:
        results = {
            filename: self.compile(filename)
            for filename in (
                "gradients.wesl",
                "summary.wesl",
                "boundary.wesl",
                "points.wesl",
            )
        }
        update_results = [self.compile("update.wesl", rule) for rule in self.rules]
        modules = {
            filename: self.device.create_shader_module(code=result.wgsl)
            for filename, result in results.items()
        }
        update_modules = [
            self.device.create_shader_module(code=result.wgsl)
            for result in update_results
        ]
        gradient_pipeline = self.device.create_compute_pipeline(
            layout="auto",
            compute={"module": modules["gradients.wesl"], "entry_point": "main"},
        )
        summary_pipeline = self.device.create_compute_pipeline(
            layout="auto",
            compute={"module": modules["summary.wesl"], "entry_point": "main"},
        )
        update_pipelines = [
            self.device.create_compute_pipeline(
                layout="auto",
                compute={
                    "module": module,
                    "entry_point": "main",
                    "constants": rule.constants,
                },
            )
            for rule, module in zip(self.rules, update_modules, strict=True)
        ]
        render_pipelines = [
            self.device.create_render_pipeline(
                layout="auto",
                vertex={"module": modules[filename], "entry_point": "vertex_main"},
                fragment={
                    "module": modules[filename],
                    "entry_point": "fragment_main",
                    "targets": [{"format": self.format}],
                },
            )
            for filename in ("boundary.wesl", "points.wesl")
        ]
        self.gradient_pipeline = gradient_pipeline
        self.summary_pipeline = summary_pipeline
        self.update_modules = update_modules
        self.update_pipelines = update_pipelines
        self.render_pipelines = render_pipelines
        for result in [*results.values(), *update_results]:
            for source in result.sources.values():
                if source.filename is not None:
                    path = Path(source.filename)
                    self.modified.setdefault(path, path.stat().st_mtime_ns)

    def apply_constants(self) -> None:
        update_pipelines = [
            self.device.create_compute_pipeline(
                layout="auto",
                compute={
                    "module": module,
                    "entry_point": "main",
                    "constants": rule.constants,
                },
            )
            for rule, module in zip(self.rules, self.update_modules, strict=True)
        ]
        self.update_pipelines = update_pipelines
        self.bind()

    def changed(self) -> bool:
        try:
            modified = {path: path.stat().st_mtime_ns for path in self.modified}
        except FileNotFoundError:
            return False
        changed = modified != self.modified
        self.modified = modified
        return changed

    def reset(
        self, samples: NDArray[np.float32], parameters: NDArray[np.float32]
    ) -> None:
        for buffer in self.buffers:
            buffer.destroy()
        parameter_count = self.layout["parameter_count"]
        self.sample_count = len(samples)
        self.samples = self.device.create_buffer_with_data(
            data=samples, usage=wgpu.BufferUsage.STORAGE
        )
        self.parameters = [
            self.device.create_buffer_with_data(
                data=parameters,
                usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
            )
            for _ in self.rules
        ]
        self.gradients = [
            self.device.create_buffer(
                size=self.sample_count * parameter_count * 4,
                usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
            )
            for _ in self.rules
        ]
        self.moments = [
            self.device.create_buffer(
                size=parameter_count * 16, usage=wgpu.BufferUsage.STORAGE
            )
            for _ in self.rules
        ]
        self.scores = [
            self.device.create_buffer(
                size=self.sample_count * 8, usage=wgpu.BufferUsage.STORAGE
            )
            for _ in self.rules
        ]
        self.histories = [
            self.device.create_buffer(
                size=300 * 16,
                usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
            )
            for _ in self.rules
        ]
        self.buffers = [
            self.samples,
            *self.parameters,
            *self.gradients,
            *self.moments,
            *self.scores,
            *self.histories,
        ]
        self.step = 0
        self.frame = 0
        self.bind()

    def bind_group(
        self,
        pipeline: wgpu.GPUComputePipeline | wgpu.GPURenderPipeline,
        resources: dict[int, wgpu.GPUBuffer],
    ) -> wgpu.GPUBindGroup:
        return self.device.create_bind_group(
            layout=pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": binding, "resource": {"buffer": buffer}}
                for binding, buffer in resources.items()
            ],
        )

    def bind(self) -> None:
        self.bindings = []
        for index, update_pipeline in enumerate(self.update_pipelines):
            parameters = self.parameters[index]
            gradients = self.gradients[index]
            scores = self.scores[index]
            self.bindings.append(
                {
                    "gradients": self.bind_group(
                        self.gradient_pipeline,
                        {0: parameters, 1: self.samples, 2: gradients, 3: scores},
                    ),
                    "update": self.bind_group(
                        update_pipeline,
                        {
                            0: parameters,
                            1: gradients,
                            2: self.moments[index],
                            3: self.learning_rates[index],
                        },
                    ),
                    "summary": self.bind_group(
                        self.summary_pipeline,
                        {0: scores, 1: self.histories[index], 2: self.progress},
                    ),
                    "boundary": self.bind_group(
                        self.render_pipelines[0], {0: parameters}
                    ),
                    "points": self.bind_group(
                        self.render_pipelines[1], {0: parameters, 1: self.samples}
                    ),
                }
            )

    def train(self, step_count: int) -> None:
        for rule, buffer in zip(self.rules, self.learning_rates, strict=True):
            self.device.queue.write_buffer(
                buffer, 0, np.array([rule.learning_rate], dtype=np.float32)
            )
        self.step += step_count
        self.device.queue.write_buffer(
            self.progress, 0, np.array([self.frame, self.step - 1], dtype=np.uint32)
        )
        self.frame += 1
        encoder = self.device.create_command_encoder()
        for _ in range(step_count):
            for update_pipeline, bindings in zip(
                self.update_pipelines, self.bindings, strict=True
            ):
                compute_pass = encoder.begin_compute_pass()
                compute_pass.set_pipeline(self.gradient_pipeline)
                compute_pass.set_bind_group(0, bindings["gradients"])
                compute_pass.dispatch_workgroups((self.sample_count + 63) // 64)
                compute_pass.end()
                compute_pass = encoder.begin_compute_pass()
                compute_pass.set_pipeline(update_pipeline)
                compute_pass.set_bind_group(0, bindings["update"])
                compute_pass.dispatch_workgroups(
                    (self.layout["parameter_count"] + 63) // 64
                )
                compute_pass.end()
        for bindings in self.bindings:
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.summary_pipeline)
            compute_pass.set_bind_group(0, bindings["summary"])
            compute_pass.dispatch_workgroups(1)
            compute_pass.end()
        self.device.queue.submit([encoder.finish()])

    def read(self, buffer: wgpu.GPUBuffer) -> NDArray[np.float32]:
        return np.frombuffer(self.device.queue.read_buffer(buffer), dtype=np.float32)

    def read_histories(self) -> list[NDArray[np.float32]]:
        histories = []
        for buffer in self.histories:
            history = self.read(buffer).reshape(-1, 4)
            history = history[history[:, 3] == 1]
            histories.append(history[np.argsort(history[:, 2])])
        return histories

    def draw(self, viewports: list[tuple[float, float, float, float]]) -> None:
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
            for bindings, viewport in zip(self.bindings, viewports, strict=True):
                render_pass.set_viewport(*viewport, 0.0, 1.0)
                render_pass.set_pipeline(self.render_pipelines[0])
                render_pass.set_bind_group(0, bindings["boundary"])
                render_pass.draw(3)
                render_pass.set_pipeline(self.render_pipelines[1])
                render_pass.set_bind_group(0, bindings["points"])
                render_pass.draw(6, self.sample_count)
        render_pass.end()
        self.device.queue.submit([encoder.finish()])
