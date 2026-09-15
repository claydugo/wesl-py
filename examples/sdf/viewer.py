# ruff: noqa: D101, D102

import math
from pathlib import Path
from time import perf_counter
from typing import cast

import numpy
import wesl
import wgpu
from imgui_bundle import imgui
from rendercanvas import BaseRenderCanvas
from wgpu.utils import get_default_device
from wgpu.utils.imgui import ImguiRenderer


class Viewer:
    def __init__(self, canvas: BaseRenderCanvas) -> None:
        self.canvas = canvas
        self.device = get_default_device()
        self.context = canvas.get_wgpu_context()
        self.format = self.context.get_preferred_format(self.device.adapter)
        self.context.configure(device=self.device, format=self.format)
        self.parameters = numpy.zeros((7, 4), dtype=numpy.float32)
        self.parameters[1] = (0.35, 0.48, 0.7, 0.0)
        self.parameters[6] = (0.55, 5.0, 0.0, 0.0)
        self.uniforms = self.device.create_buffer_with_data(
            data=self.parameters,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self.particle_count = 2048
        self.particles = self.device.create_buffer(
            size=self.particle_count * 32,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        self.pipelines = {}
        directory = Path(__file__).parent
        for cutout in (False, True):
            options = wesl.CompileOptions(
                features=wesl.Features(flags={"cutout": cutout})
            )
            simulation_module = self.device.create_shader_module(
                code=wesl.compile_file(
                    directory / "simulate.wesl",
                    root_directory=directory.parent,
                    options=options,
                ).wgsl
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
            surface_module = self.device.create_shader_module(
                code=wesl.compile_file(
                    directory / "render.wesl",
                    root_directory=directory.parent,
                    options=options,
                ).wgsl
            )
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
        particle_module = self.device.create_shader_module(
            code=wesl.compile_file(
                directory / "particles.wesl", root_directory=directory.parent
            ).wgsl
        )
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
        self.cutout = True
        self.paused = False
        self.reset = False
        self.orbit = [0.35, 0.2, 7.8]
        self.pointer = None
        self.previous_time = perf_counter()
        self.elapsed = 0.0
        self.depth_texture = None
        self.gui = ImguiRenderer(self.device, canvas, render_target_format=self.format)
        imgui.style_colors_dark()
        imgui.get_io().font_default = imgui.get_io().fonts.add_font_default_vector()
        imgui.get_style().font_size_base = 16
        imgui.get_style().frame_padding = imgui.ImVec2(6, 4)
        imgui.get_style().item_spacing = imgui.ImVec2(8, 8)
        self.gui.set_gui(self.draw_controls)
        canvas.add_event_handler(
            self.move_camera, "pointer_down", "pointer_up", "pointer_move", "wheel"
        )
        canvas.request_draw(self.draw_frame)

    def move_camera(self, event: dict) -> None:
        if event["event_type"] == "pointer_down" and event["button"] == 1:
            self.pointer = (event["x"], event["y"])
        elif event["event_type"] == "pointer_up":
            self.pointer = None
        elif event["event_type"] == "pointer_move" and self.pointer is not None:
            if 1 not in event["buttons"]:
                self.pointer = None
                return
            self.orbit[0] -= (event["x"] - self.pointer[0]) * 0.008
            self.orbit[1] = numpy.clip(
                self.orbit[1] + (event["y"] - self.pointer[1]) * 0.008, -0.1, 1.3
            )
            self.pointer = (event["x"], event["y"])
        elif event["event_type"] == "wheel":
            self.orbit[2] = numpy.clip(
                self.orbit[2] * math.exp(event["dy"] * 0.001), 4.0, 14.0
            )

    def draw_controls(self) -> None:
        imgui.set_next_window_pos((16, 16), imgui.Cond_.always)
        imgui.set_next_window_size((280, 0), imgui.Cond_.always)
        imgui.begin(
            "SDF playground",
            flags=imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_collapse,
        )
        imgui.text_wrapped("Sculpt a surface and watch particles bounce off it.")
        imgui.spacing()
        imgui.push_item_width(120)
        _, self.parameters[1, 2] = imgui.slider_float(
            "Separation", float(self.parameters[1, 2]), 0.25, 1.3
        )
        _, self.parameters[1, 0] = imgui.slider_float(
            "Blend", float(self.parameters[1, 0]), 0.02, 0.65
        )
        _, self.cutout = imgui.checkbox("Cut a tunnel", self.cutout)
        if self.cutout:
            _, self.parameters[1, 1] = imgui.slider_float(
                "Tunnel radius", float(self.parameters[1, 1]), 0.1, 0.85
            )
        imgui.separator()
        _, self.parameters[6, 0] = imgui.slider_float(
            "Bounce", float(self.parameters[6, 0]), 0.0, 0.95
        )
        _, self.parameters[6, 1] = imgui.slider_float(
            "Gravity", float(self.parameters[6, 1]), 1.0, 10.0
        )
        _, self.paused = imgui.checkbox("Pause", self.paused)
        if imgui.button("Reset particles"):
            self.reset = True
        imgui.separator()
        imgui.text_wrapped("Drag the scene to orbit. Scroll to zoom.")
        if imgui.button("Reset view"):
            self.orbit = [0.35, 0.2, 7.8]
        imgui.pop_item_width()
        imgui.end()

    def draw_frame(self) -> None:
        current_time = perf_counter()
        delta = 0.0 if self.paused else min(current_time - self.previous_time, 1 / 30)
        self.previous_time = current_time
        self.elapsed += delta
        width, height = self.canvas.get_physical_size()
        if width == 0 or height == 0:
            self.canvas.request_draw()
            return
        self.parameters[0] = (width, height, self.elapsed, delta)
        yaw, pitch, distance = self.orbit
        forward = -numpy.array(
            [
                math.sin(yaw) * math.cos(pitch),
                math.sin(pitch),
                math.cos(yaw) * math.cos(pitch),
            ]
        )
        right = numpy.cross(forward, [0, 1, 0])
        right /= numpy.linalg.norm(right)
        self.parameters[2, :3] = numpy.array([0, 0.8, 0]) - forward * distance
        self.parameters[3, :3] = right
        self.parameters[4, :3] = numpy.cross(right, forward)
        self.parameters[5, :3] = forward
        self.parameters[6, 2] = self.reset
        self.reset = False
        self.device.queue.write_buffer(self.uniforms, 0, self.parameters)
        if self.depth_texture is None or self.depth_texture.size[:2] != (width, height):
            if self.depth_texture is not None:
                self.depth_texture.destroy()
            self.depth_texture = self.device.create_texture(
                size=(width, height, 1),
                format="depth32float",
                usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            )
        simulation_pipeline, simulation_bindings, surface_pipeline, surface_bindings = (
            self.pipelines[self.cutout]
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
        self.gui.render()
        self.canvas.request_draw()
