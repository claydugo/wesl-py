# ruff: noqa: D101, D102

import math
from pathlib import Path
from time import perf_counter
from typing import cast

import imageio.v3 as imageio
import numpy
import wgpu
from imgui_bundle import imgui
from rendercanvas import BaseRenderCanvas
from wgpu.utils.imgui import ImguiRenderer

from examples.lygia.renderer import Renderer


class Viewer:
    def __init__(
        self,
        canvas: BaseRenderCanvas,
        device: wgpu.GPUDevice,
        *,
        library_directory: Path,
        seed: int = 17,
    ) -> None:
        self.canvas = canvas
        self.device = device
        self.context = canvas.get_wgpu_context()
        self.format = self.context.get_preferred_format(device.adapter)
        self.context.configure(
            device=device,
            format=self.format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        self.renderer = Renderer(device, self.format, library_directory)
        self.seed = int(numpy.int32(seed))
        self.center = numpy.zeros(2, dtype=numpy.float64)
        self.scale = 3.4
        self.roughness = 0.38
        self.water_level = 0.52
        self.palette = 0
        self.contours = 0.5
        self.relief = 0.65
        self.animated = False
        self.speed = 0.35
        self.elapsed = 0.0
        self.previous_time = perf_counter()
        self.pointer = None
        self.save_requested = False
        self.saved = False
        self.parameters = numpy.zeros((3, 4), dtype=numpy.float32)
        self.gui = ImguiRenderer(device, canvas, render_target_format=self.format)
        imgui.style_colors_dark()
        imgui.get_io().font_default = imgui.get_io().fonts.add_font_default_vector()
        style = imgui.get_style()
        style.font_size_base = 16
        style.window_padding = imgui.ImVec2(20, 20)
        style.frame_padding = imgui.ImVec2(8, 6)
        style.item_spacing = imgui.ImVec2(8, 12)
        style.window_rounding = 12
        style.frame_rounding = 5
        style.grab_rounding = 4
        style.set_color_(imgui.Col_.window_bg, (0.035, 0.06, 0.075, 1))
        style.set_color_(imgui.Col_.text, (0.9, 0.9, 0.84, 1))
        style.set_color_(imgui.Col_.text_disabled, (0.47, 0.58, 0.59, 1))
        style.set_color_(imgui.Col_.frame_bg, (0.10, 0.16, 0.18, 1))
        style.set_color_(imgui.Col_.frame_bg_hovered, (0.15, 0.24, 0.26, 1))
        style.set_color_(imgui.Col_.frame_bg_active, (0.17, 0.29, 0.30, 1))
        style.set_color_(imgui.Col_.slider_grab, (0.73, 0.68, 0.48, 1))
        style.set_color_(imgui.Col_.slider_grab_active, (0.91, 0.83, 0.57, 1))
        style.set_color_(imgui.Col_.button, (0.13, 0.22, 0.24, 1))
        style.set_color_(imgui.Col_.button_hovered, (0.20, 0.33, 0.34, 1))
        style.set_color_(imgui.Col_.button_active, (0.24, 0.39, 0.39, 1))
        style.set_color_(imgui.Col_.check_mark, (0.91, 0.83, 0.57, 1))
        self.gui.set_gui(self.draw_controls)
        canvas.add_event_handler(
            self.move_camera, "pointer_down", "pointer_up", "pointer_move", "wheel"
        )
        canvas.request_draw(self.draw_frame)

    def move_camera(self, event: dict) -> None:
        if event["event_type"] == "pointer_up":
            self.pointer = None
            return
        imgui.set_current_context(self.gui.imgui_context)
        if imgui.get_io().want_capture_mouse:
            return
        _, height = self.canvas.get_logical_size()
        if height == 0:
            return
        if event["event_type"] == "pointer_down" and event["button"] == 1:
            self.pointer = (event["x"], event["y"])
        elif event["event_type"] == "pointer_move" and self.pointer is not None:
            if 1 not in event["buttons"]:
                self.pointer = None
                return
            self.center -= (numpy.array([event["x"], event["y"]]) - self.pointer) * (
                self.scale / height
            )
            self.pointer = (event["x"], event["y"])
        elif event["event_type"] == "wheel":
            previous_scale = self.scale
            self.scale = float(
                numpy.clip(self.scale * math.exp(event["dy"] * 0.001), 0.35, 12.0)
            )
            position = numpy.array([event["x"], event["y"]], dtype=numpy.float64)
            position -= numpy.array(self.canvas.get_logical_size()) * 0.5
            self.center += position / height * (previous_scale - self.scale)

    def draw_controls(self) -> None:
        _, height = self.canvas.get_logical_size()
        imgui.set_next_window_pos((24, 24), imgui.Cond_.always)
        imgui.set_next_window_size((280, min(660, height - 48)), imgui.Cond_.always)
        imgui.begin(
            "Landscape",
            flags=imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_collapse,
        )
        imgui.push_font(None, 26)
        imgui.text("ARCHIPELAGO")
        imgui.pop_font()
        imgui.text_disabled("Shape a landscape.")
        imgui.spacing()
        imgui.separator_text("Terrain")
        imgui.set_next_item_width(150)
        _, self.seed = imgui.input_int("Seed", self.seed)
        imgui.set_next_item_width(150)
        _, self.scale = imgui.slider_float("Scale", self.scale, 0.35, 12.0, "%.2f")
        imgui.set_next_item_width(150)
        _, self.roughness = imgui.slider_float(
            "Roughness", self.roughness, 0.2, 0.7, "%.2f"
        )
        imgui.set_next_item_width(150)
        _, self.water_level = imgui.slider_float(
            "Water", self.water_level, 0.2, 0.75, "%.2f"
        )
        imgui.separator_text("Appearance")
        imgui.set_next_item_width(150)
        _, self.palette = imgui.combo(
            "Palette", self.palette, ["Coast", "Copper", "Ink"]
        )
        imgui.set_next_item_width(150)
        _, self.contours = imgui.slider_float(
            "Contours", self.contours, 0.0, 1.0, "%.2f"
        )
        imgui.set_next_item_width(150)
        _, self.relief = imgui.slider_float("Relief", self.relief, 0.0, 1.0, "%.2f")
        imgui.separator_text("Motion")
        _, self.animated = imgui.checkbox("Evolve", self.animated)
        imgui.begin_disabled(not self.animated)
        imgui.set_next_item_width(150)
        _, self.speed = imgui.slider_float("Speed", self.speed, 0.05, 1.0, "%.2f")
        imgui.end_disabled()
        imgui.spacing()
        if imgui.button("Reset view", (112, 32)):
            self.center[:] = 0
            self.scale = 3.4
        imgui.same_line()
        if imgui.button("Save PNG", (112, 32)):
            self.save_requested = True
        imgui.text_disabled("Drag to pan. Scroll to zoom.")
        if self.saved:
            imgui.text_disabled("Saved landscape.png")
        imgui.end()

    def draw_frame(self) -> None:
        current_time = perf_counter()
        if self.animated:
            self.elapsed += min(current_time - self.previous_time, 1 / 30) * self.speed
        self.previous_time = current_time
        width, height = self.canvas.get_physical_size()
        if width == 0 or height == 0:
            self.canvas.request_draw()
            return
        self.parameters[0, :3] = (width, height, self.elapsed)
        self.parameters.view(numpy.int32)[0, 3] = self.seed
        self.parameters[1] = (*self.center, self.scale, self.roughness)
        self.parameters[2] = (
            self.water_level,
            self.palette,
            self.contours,
            self.relief,
        )
        target = cast("wgpu.GPUTexture", self.context.get_current_texture())
        self.renderer.render(target, self.parameters)
        if self.save_requested:
            pixels = numpy.frombuffer(
                self.device.queue.read_texture(
                    {"texture": target}, {"bytes_per_row": width * 4}, target.size
                ),
                dtype=numpy.uint8,
            ).reshape(height, width, 4)
            if self.format.startswith("bgra"):
                pixels = pixels[..., [2, 1, 0, 3]]
            imageio.imwrite("landscape.png", pixels)
            self.save_requested = False
            self.saved = True
        self.gui.render()
        self.canvas.request_draw()
