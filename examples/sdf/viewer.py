import math
from time import perf_counter

import numpy as np
from imgui_bundle import imgui
from rendercanvas import BaseRenderCanvas
from wgpu.utils.imgui import ImguiRenderer

from examples.sdf.renderer import Renderer
from examples.style import apply_style


class Viewer:
    def __init__(self, canvas: BaseRenderCanvas) -> None:
        self.canvas = canvas
        self.parameters = np.zeros((7, 4), dtype=np.float32)
        self.parameters[1] = (0.35, 0.48, 0.7, 0.0)
        self.parameters[6] = (0.55, 5.0, 0.0, 0.0)
        self.renderer = Renderer(canvas, self.parameters)
        self.cutout = True
        self.paused = False
        self.reset = False
        self.orbit = [0.35, 0.2, 7.8]
        self.pointer = None
        self.previous_time = perf_counter()
        self.elapsed = 0.0
        self.gui = ImguiRenderer(
            self.renderer.device, canvas, render_target_format=self.renderer.format
        )
        apply_style()
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
            self.orbit[1] = np.clip(
                self.orbit[1] + (event["y"] - self.pointer[1]) * 0.008, -0.1, 1.3
            )
            self.pointer = (event["x"], event["y"])
        elif event["event_type"] == "wheel":
            self.orbit[2] = np.clip(
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
        forward = -np.array(
            [
                math.sin(yaw) * math.cos(pitch),
                math.sin(pitch),
                math.cos(yaw) * math.cos(pitch),
            ]
        )
        right = np.cross(forward, [0, 1, 0])
        right /= np.linalg.norm(right)
        self.parameters[2, :3] = np.array([0, 0.8, 0]) - forward * distance
        self.parameters[3, :3] = right
        self.parameters[4, :3] = np.cross(right, forward)
        self.parameters[5, :3] = forward
        self.parameters[6, 2] = self.reset
        self.reset = False
        self.renderer.draw(self.parameters, cutout=self.cutout)
        self.gui.render()
        self.canvas.request_draw()
