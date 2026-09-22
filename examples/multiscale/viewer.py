# ruff: noqa: D101, D102

import numpy
import pygfx
from imgui_bundle import imgui
from rendercanvas import BaseRenderCanvas
from wgpu.utils.imgui import ImguiRenderer

from examples.common import composite
from examples.multiscale.compute import enhance


class Viewer:
    def __init__(
        self,
        canvas: BaseRenderCanvas,
        channels: numpy.ndarray,
        colors: numpy.ndarray,
        labels: list[str],
    ) -> None:
        self.canvas = canvas
        self.channels = channels
        self.colors = colors
        self.labels = labels
        self.renderer = pygfx.WgpuRenderer(self.canvas)
        _, self.height, self.width = self.channels.shape
        self.weights = numpy.array([0.12, 1.5, 1.5, 0], dtype=numpy.float32)
        self.visible = [True, True, True]
        self.settings = {
            "sigma": 6.0,
            "strength": 3.0,
            "tiled": False,
            "process": False,
            "color": False,
        }
        self.source, self.fine, self.coarse, self.output = enhance(
            self.channels, 6.0, 3.0
        )
        original_texture, self.original_shader, self.original_weights = composite(
            self.source, self.colors, self.weights, (self.width, self.height)
        )
        processed_texture, self.processed_shader, self.processed_weights = composite(
            self.output, self.colors, self.weights, (self.width, self.height)
        )

        self.scenes = []
        self.cameras = []
        self.viewports = []
        for texture in (original_texture, processed_texture):
            scene = pygfx.Scene()
            scene.add(pygfx.Background.from_color("#0c1017"))
            image = pygfx.Image(
                pygfx.Geometry(grid=texture), pygfx.ImageBasicMaterial(clim=(0, 255))
            )
            image.local.scale_y = -1
            scene.add(image)
            camera = pygfx.OrthographicCamera()
            camera.show_object(image, match_aspect=True)
            self.scenes.append(scene)
            self.cameras.append(camera)
            self.viewports.append(pygfx.Viewport(self.renderer))
        self.controller = pygfx.PanZoomController(self.cameras[0])
        self.controller.add_camera(self.cameras[1])
        self.controller.register_events(self.viewports[0])
        self.controller.register_events(self.viewports[1])

        self.gui_renderer = ImguiRenderer(self.renderer.device, self.canvas)
        imgui.style_colors_dark()
        imgui.get_io().font_default = imgui.get_io().fonts.add_font_default_vector()
        imgui.get_style().font_size_base = 16
        imgui.get_style().frame_padding = imgui.ImVec2(6, 4)
        imgui.get_style().item_spacing = imgui.ImVec2(8, 8)
        self.gui_renderer.set_gui(self.draw_controls)

        self.canvas.request_draw(self.draw_frame)

    def draw_controls(self) -> None:
        canvas_width, canvas_height = self.canvas.get_logical_size()
        imgui.set_next_window_pos((16, 16), imgui.Cond_.always)
        imgui.set_next_window_size((288, canvas_height - 32), imgui.Cond_.always)
        imgui.begin(
            "Multiscale fluorescence",
            flags=imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_collapse,
        )
        imgui.text_wrapped(
            "Explore fine branches and broad structures in the fluorescence channels."
        )
        imgui.spacing()
        changed, self.settings["sigma"] = imgui.slider_float(
            "Scale", float(self.settings["sigma"]), 0.7, 12.0, "%.1f px"
        )
        if changed:
            self.settings["process"] = True
        changed, self.settings["strength"] = imgui.slider_float(
            "Strength", float(self.settings["strength"]), 0.0, 6.0
        )
        if changed:
            self.settings["process"] = True
        changed, self.settings["tiled"] = imgui.checkbox(
            "Use tiled convolution", bool(self.settings["tiled"])
        )
        if changed:
            self.settings["process"] = True
        imgui.separator()
        imgui.text("Channels")
        for channel, label in enumerate(self.labels):
            imgui.push_id(channel)
            changed, self.visible[channel] = imgui.checkbox(
                label, self.visible[channel]
            )
            if changed:
                self.settings["color"] = True
            changed, self.weights[channel] = imgui.slider_float(
                "Gain", float(self.weights[channel]), 0.0, 3.0
            )
            if changed:
                self.settings["color"] = True
            imgui.pop_id()
        imgui.separator()
        imgui.text_wrapped("Drag either image to pan. Scroll to zoom both views.")
        if imgui.button("Reset view"):
            for camera, scene in zip(self.cameras, self.scenes, strict=True):
                camera.show_object(scene.children[1], match_aspect=True)
        imgui.spacing()
        imgui.text_wrapped(
            "Brightfield stays unchanged. The fluorescence channels use "
            "a difference of Gaussian scales."
        )
        imgui.end()
        panel_width = (canvas_width - 336) / 2
        for index, title in enumerate(("Original composite", "Enhanced fluorescence")):
            imgui.set_next_window_pos(
                (320 + index * panel_width, 16), imgui.Cond_.always
            )
            imgui.set_next_window_size((panel_width - 8, 44), imgui.Cond_.always)
            imgui.begin(
                title,
                flags=imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_inputs,
            )
            imgui.text(title)
            imgui.end()

    def draw_frame(self) -> None:
        if self.settings["process"]:
            _, _, _, result = enhance(
                self.channels,
                float(self.settings["sigma"]),
                float(self.settings["strength"]),
                tiled=bool(self.settings["tiled"]),
            )
            self.processed_shader.set_resource(0, result)
            self.processed_shader.dispatch(
                (self.width + 15) // 16, (self.height + 15) // 16
            )
            self.settings["process"] = False
        if self.settings["color"]:
            displayed_weights = self.weights.copy()
            displayed_weights[:3] *= self.visible
            for shader, parameters in (
                (self.original_shader, self.original_weights),
                (self.processed_shader, self.processed_weights),
            ):
                self.renderer.device.queue.write_buffer(
                    parameters, 0, displayed_weights
                )
                shader.dispatch((self.width + 15) // 16, (self.height + 15) // 16)
            self.settings["color"] = False
        canvas_width, canvas_height = self.canvas.get_logical_size()
        panel_width = (canvas_width - 336) / 2
        for index, (viewport, scene, camera) in enumerate(
            zip(self.viewports, self.scenes, self.cameras, strict=True)
        ):
            viewport.rect = (
                320 + index * panel_width,
                68,
                panel_width - 8,
                canvas_height - 84,
            )
            viewport.render(scene, camera)
        self.renderer.flush()
        self.gui_renderer.render()
        self.canvas.request_draw()
