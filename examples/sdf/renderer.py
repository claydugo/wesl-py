# ruff: noqa: D101, D102

from pathlib import Path
from typing import cast

import numpy
import wesl
import wgpu
from rendercanvas import BaseRenderCanvas
from wgpu.utils import get_default_device


def create_shader(
    device: wgpu.GPUDevice, filename: str, **features: bool
) -> wgpu.GPUShaderModule:
    directory = Path(__file__).parent
    result = wesl.compile_file(
        directory / "shaders" / filename,
        root_directory=directory.parent.parent,
        options=wesl.CompileOptions(
            visibility=True, features=wesl.Features(flags=dict(features))
        ),
    )
    return device.create_shader_module(code=result.wgsl)


class Renderer:
    def __init__(self, canvas: BaseRenderCanvas, parameters: numpy.ndarray) -> None:
        self.canvas = canvas
        self.device = get_default_device()
        self.context = canvas.get_wgpu_context()
        self.format = self.context.get_preferred_format(self.device.adapter)
        self.context.configure(device=self.device, format=self.format)
        self.uniforms = self.device.create_buffer_with_data(
            data=parameters,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self.particle_count = 2048
        self.particles = self.device.create_buffer(
            size=self.particle_count * 32,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        self.pipelines = {}
        for cutout in (False, True):
            simulation_module = create_shader(
                self.device, "simulate.wesl", cutout=cutout
            )
            simulation_pipeline = self.device.create_compute_pipeline(
                layout="auto",
                compute={"module": simulation_module, "entry_point": "main"},
            )
            simulation_bindings = self.device.create_bind_group(
                layout=simulation_pipeline.get_bind_group_layout(0),
                entries=[
                    {"binding": 0, "resource": {"buffer": self.uniforms}},
                    {"binding": 1, "resource": {"buffer": self.particles}},
                ],
            )
            surface_module = create_shader(self.device, "render.wesl", cutout=cutout)
            surface_pipeline = self.device.create_render_pipeline(
                layout="auto",
                vertex={"module": surface_module, "entry_point": "vertex_main"},
                fragment={
                    "module": surface_module,
                    "entry_point": "fragment_main",
                    "targets": [{"format": self.format}],
                },
                depth_stencil={
                    "format": "depth32float",
                    "depth_write_enabled": True,
                    "depth_compare": "less-equal",
                },
            )
            surface_bindings = self.device.create_bind_group(
                layout=surface_pipeline.get_bind_group_layout(0),
                entries=[{"binding": 0, "resource": {"buffer": self.uniforms}}],
            )
            self.pipelines[cutout] = (
                simulation_pipeline,
                simulation_bindings,
                surface_pipeline,
                surface_bindings,
            )
        particle_module = create_shader(self.device, "particles.wesl")
        self.particle_pipeline = self.device.create_render_pipeline(
            layout="auto",
            vertex={"module": particle_module, "entry_point": "vertex_main"},
            fragment={
                "module": particle_module,
                "entry_point": "fragment_main",
                "targets": [{"format": self.format}],
            },
            depth_stencil={
                "format": "depth32float",
                "depth_write_enabled": True,
                "depth_compare": "less",
            },
        )
        self.particle_bindings = self.device.create_bind_group(
            layout=self.particle_pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": 0, "resource": {"buffer": self.uniforms}},
                {"binding": 1, "resource": {"buffer": self.particles}},
            ],
        )
        self.depth_texture = None

    def draw(self, parameters: numpy.ndarray, *, cutout: bool) -> None:
        width, height = self.canvas.get_physical_size()
        self.device.queue.write_buffer(self.uniforms, 0, parameters)
        if self.depth_texture is None or self.depth_texture.size[:2] != (width, height):
            if self.depth_texture is not None:
                self.depth_texture.destroy()
            self.depth_texture = self.device.create_texture(
                size=(width, height, 1),
                format="depth32float",
                usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            )
        simulation_pipeline, simulation_bindings, surface_pipeline, surface_bindings = (
            self.pipelines[cutout]
        )
        encoder = self.device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(simulation_pipeline)
        compute_pass.set_bind_group(0, simulation_bindings)
        compute_pass.dispatch_workgroups((self.particle_count + 63) // 64)
        compute_pass.end()
        target = cast("wgpu.GPUTexture", self.context.get_current_texture())
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": target.create_view(),
                    "resolve_target": None,
                    "load_op": "clear",
                    "store_op": "store",
                    "clear_value": (0.035, 0.05, 0.08, 1.0),
                }
            ],
            depth_stencil_attachment={
                "view": self.depth_texture.create_view(),
                "depth_load_op": "clear",
                "depth_store_op": "store",
                "depth_clear_value": 1.0,
            },
        )
        render_pass.set_pipeline(surface_pipeline)
        render_pass.set_bind_group(0, surface_bindings)
        render_pass.draw(3)
        render_pass.set_pipeline(self.particle_pipeline)
        render_pass.set_bind_group(0, self.particle_bindings)
        render_pass.draw(6, self.particle_count)
        render_pass.end()
        self.device.queue.submit([encoder.finish()])
