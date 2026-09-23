# ruff: noqa: D101, D102

from pathlib import Path

import numpy
import wesl
import wgpu


class Renderer:
    def __init__(
        self, device: wgpu.GPUDevice, texture_format: str, library_directory: Path
    ) -> None:
        self.device = device
        directory = Path(__file__).parent
        result = wesl.compile_file(
            directory / "shaders/landscape.wesl",
            root_directory=directory.parent,
            dependencies={"lygia": library_directory},
            options=wesl.CompileOptions(
                features=wesl.Features(
                    flags={"srgb_target": texture_format.endswith("-srgb")}
                )
            ),
        )
        module = device.create_shader_module(code=result.wgsl)
        self.pipeline = device.create_render_pipeline(
            layout="auto",
            vertex={"module": module, "entry_point": "vertex_main"},
            fragment={
                "module": module,
                "entry_point": "fragment_main",
                "targets": [{"format": texture_format}],
            },
        )
        self.uniforms = device.create_buffer(
            size=48, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self.bindings = device.create_bind_group(
            layout=self.pipeline.get_bind_group_layout(0),
            entries=[{"binding": 0, "resource": {"buffer": self.uniforms}}],
        )

    def render(self, target: wgpu.GPUTexture, parameters: numpy.ndarray) -> None:
        self.device.queue.write_buffer(self.uniforms, 0, parameters)
        encoder = self.device.create_command_encoder()
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": target.create_view(),
                    "load_op": "clear",
                    "store_op": "store",
                    "clear_value": (0, 0, 0, 1),
                }
            ]
        )
        render_pass.set_pipeline(self.pipeline)
        render_pass.set_bind_group(0, self.bindings)
        render_pass.draw(3)
        render_pass.end()
        self.device.queue.submit([encoder.finish()])
