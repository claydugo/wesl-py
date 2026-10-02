from enum import StrEnum

import numpy as np
import pygfx
import wgpu
from imgui_bundle import imgui
from rendercanvas import BaseRenderCanvas
from wgpu.utils.imgui import ImguiRenderer

from examples.multiscale.common import composite
from examples.multiscale.compute import (
    analyze,
    create_shader,
    distance_field,
    enhance,
    smooth,
    unwrap,
)


class Analysis(StrEnum):
    ENHANCEMENT = "Enhanced fluorescence"
    CORRELATION = "Channel correlation"
    DISTANCE = "Perimeter distance"
    POLAR = "Polar view"


class Viewer:
    def __init__(
        self,
        canvas: BaseRenderCanvas,
        channels: np.ndarray,
        colors: np.ndarray,
        labels: list[str],
    ) -> None:
        self.canvas = canvas
        self.channels = channels
        self.labels = labels
        self.renderer = pygfx.WgpuRenderer(self.canvas)
        _, self.height, self.width = self.channels.shape
        self.weights = np.array([0.12, 1.5, 1.5, 0], dtype=np.float32)
        self.visible = [True, True, True]
        self.mode = Analysis.ENHANCEMENT
        self.modes = list(Analysis)
        self.settings = {
            "sigma": 6.0,
            "strength": 3.0,
            "process": False,
            "color": False,
            "display": False,
            "minimum_signal": 0.06,
            "maximum_brightfield": 0.9,
            "opacity": 0.85,
            "spacing": 20.0,
            "center_x": (self.width - 1) / 2,
            "center_y": (self.height - 1) / 2,
            "maximum_radius": min(self.width, self.height) / 2,
        }
        self.radial_profiles = None
        self.distance_profiles = None
        self.analysis_shader = None
        self._create_resources(colors)
        self._create_views()

        self.gui_renderer = ImguiRenderer(self.renderer.device, self.canvas)
        imgui.style_colors_dark()
        imgui.get_io().font_default = imgui.get_io().fonts.add_font_default_vector()
        imgui.get_style().font_size_base = 16
        imgui.get_style().frame_padding = imgui.ImVec2(6, 4)
        imgui.get_style().item_spacing = imgui.ImVec2(8, 8)
        self.gui_renderer.set_gui(self.draw_controls)
        self.canvas.request_draw(self.draw_frame)

    def _create_resources(self, colors: np.ndarray) -> None:
        self.source, self.fine, self.coarse, self.enhanced = enhance(
            self.channels, 6.0, 3.0
        )
        self.enhancement_sigma = 6.0
        self.enhancement_shader = create_shader("enhancement.wesl")
        self.enhancement_shader.set_resource(0, self.source)
        self.enhancement_shader.set_resource(1, self.fine)
        self.enhancement_shader.set_resource(2, self.coarse)
        self.enhancement_shader.set_resource(3, self.enhanced)
        original_texture, self.original_shader, self.original_weights = composite(
            self.source, colors, self.weights, (self.width, self.height)
        )
        processed_texture, self.processed_shader, self.processed_weights = composite(
            self.enhanced, colors, self.weights, (self.width, self.height)
        )
        self.original_texture = original_texture
        self.processed_texture = processed_texture
        self.analysis_texture = pygfx.Texture(
            dim=2,
            size=(self.width, self.height, 1),
            format="rgba8unorm",
            usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.TEXTURE_BINDING,
        )
        self.guide_texture = pygfx.Texture(
            dim=2,
            size=(self.width, self.height, 1),
            format="rgba8unorm",
            usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.TEXTURE_BINDING,
        )
        self.display_parameters = self.renderer.device.create_buffer(
            size=32, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self.guide_shader = create_shader(
            "display.wesl",
            (self.width, self.height),
            entry_point="polar_guide",
        )
        self.guide_shader.set_resource(1, original_texture)
        self.guide_shader.set_resource(2, self.guide_texture)
        self.guide_shader.set_resource(3, self.display_parameters)

    def _create_views(self) -> None:
        self.scenes = []
        self.cameras = []
        self.viewports = []
        self.geometries = []
        self.images = []
        for texture in (self.original_texture, self.processed_texture):
            scene = pygfx.Scene()
            scene.add(pygfx.Background.from_color("#0c1017"))
            geometry = pygfx.Geometry(grid=texture)
            image = pygfx.Image(geometry, pygfx.ImageBasicMaterial(clim=(0, 255)))
            image.local.scale_y = -1
            scene.add(image)
            camera = pygfx.OrthographicCamera()
            camera.show_object(image, match_aspect=True)
            self.scenes.append(scene)
            self.cameras.append(camera)
            self.viewports.append(pygfx.Viewport(self.renderer))
            self.geometries.append(geometry)
            self.images.append(image)
        self.controller = pygfx.PanZoomController(self.cameras[0])
        self.controller.add_camera(self.cameras[1])
        self.controller.register_events(self.viewports[0])
        self.controller.register_events(self.viewports[1])

    def _draw_slider(
        self,
        setting: str,
        label: str,
        bounds: tuple[float, float],
        *,
        update: str,
        format_string: str = "%.3f",
    ) -> None:
        changed, self.settings[setting] = imgui.slider_float(
            label, float(self.settings[setting]), *bounds, format_string
        )
        if changed:
            self.settings[update] = True

    def draw_controls(self) -> None:
        canvas_width, canvas_height = self.canvas.get_logical_size()
        imgui.set_next_window_pos((16, 16), imgui.Cond_.always)
        imgui.set_next_window_size(
            (288, max(1, canvas_height - 32)), imgui.Cond_.always
        )
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
        imgui.begin_disabled(self.mode == Analysis.POLAR)
        self._draw_slider(
            "sigma", "Scale", (0.7, 12.0), update="process", format_string="%.1f px"
        )
        imgui.end_disabled()
        imgui.begin_disabled(self.mode != Analysis.ENHANCEMENT)
        self._draw_slider("strength", "Strength", (0.0, 6.0), update="process")
        imgui.end_disabled()
        self._draw_channel_controls()
        self._draw_analysis_controls()
        self._draw_profiles()
        imgui.separator()
        imgui.text_wrapped("Drag either image to pan. Scroll to zoom both views.")
        if imgui.button("Reset view"):
            for camera, image in zip(self.cameras, self.images, strict=True):
                camera.show_object(image, match_aspect=True)
        imgui.spacing()
        if self.mode == Analysis.ENHANCEMENT:
            imgui.text_wrapped(
                "Brightfield stays unchanged. The fluorescence channels use "
                "a difference of Gaussian scales."
            )
        elif self.mode == Analysis.CORRELATION:
            imgui.text_wrapped(
                "Blue: negative correlation. White: zero. Red: positive. "
                "Brightfield above the cutoff is excluded from statistics. "
                "Constant neighborhoods have no overlay."
            )
        elif self.mode == Analysis.DISTANCE:
            imgui.text_wrapped(
                "Yellow: near the perimeter. Blue: far. The threshold estimates "
                "the fluorescence footprint. Distances are approximate. "
                "Profiles use original intensities inside that footprint."
            )
        else:
            imgui.text_wrapped(
                "Left to right: 0 to 360 degrees clockwise from the right. "
                "Top to bottom: center to selected radius. Profiles use raw "
                "intensity and exclude samples outside the image. "
                "They include background inside the image. Radius is not time."
            )
        imgui.end()
        panel_width = (canvas_width - 336) / 2
        if panel_width - 8 <= 0:
            return
        for index, title in enumerate(("Original composite", self.mode)):
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

    def _draw_channel_controls(self) -> None:
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

    def _draw_analysis_controls(self) -> None:
        imgui.separator()
        imgui.text("Analysis")
        imgui.set_next_item_width(-1)
        changed, selected = imgui.combo(
            "##analysis",
            self.modes.index(self.mode),
            [mode.value for mode in self.modes],
        )
        self.mode = self.modes[selected]
        if changed:
            self.settings["process"] = True
        if self.mode == Analysis.CORRELATION:
            imgui.set_next_item_width(128)
            self._draw_slider(
                "maximum_brightfield",
                "Max brightfield",
                (0.0, 1.0),
                update="process",
            )
        if self.mode == Analysis.DISTANCE:
            imgui.set_next_item_width(160)
            self._draw_slider(
                "minimum_signal", "Min signal", (0.001, 1.0), update="process"
            )
            self._draw_slider(
                "spacing",
                "Contours",
                (2.0, 100.0),
                update="display",
                format_string="%.1f px",
            )
        if self.mode in (Analysis.CORRELATION, Analysis.DISTANCE):
            self._draw_slider("opacity", "Overlay", (0.0, 1.0), update="display")
        if self.mode == Analysis.POLAR:
            self._draw_slider(
                "center_x", "Center X", (0.0, self.width - 1.0), update="process"
            )
            self._draw_slider(
                "center_y", "Center Y", (0.0, self.height - 1.0), update="process"
            )
            self._draw_slider(
                "maximum_radius",
                "Radius",
                (1.0, float(np.hypot(self.width, self.height))),
                update="process",
                format_string="%.1f px",
            )

    def _draw_profiles(self) -> None:
        if self.mode not in (Analysis.POLAR, Analysis.DISTANCE):
            return
        if self.mode == Analysis.POLAR:
            profiles = self.radial_profiles
            imgui.text("Mean intensity vs radius")
            if profiles is not None and len(profiles):
                imgui.text(f"0 to {profiles[-1, 3]:.0f} px")
        else:
            profiles = self.distance_profiles
            imgui.text_wrapped("Mean intensity vs edge distance")
            if profiles is not None and len(profiles):
                imgui.text(f"0 to {profiles[-1, 3] + profiles[0, 3]:.0f} px")
            else:
                imgui.text("No foreground above threshold.")
        if profiles is not None and len(profiles):
            for channel, label in enumerate(("GFP", "RFP")):
                imgui.plot_lines(
                    label,
                    np.ascontiguousarray(profiles[:, channel]),
                    scale_min=0.0,
                    scale_max=1.0,
                    graph_size=(180, 48),
                )

    def _update_analysis(self) -> None:
        dimensions = (self.width, self.height)
        if self.mode == Analysis.ENHANCEMENT:
            sigma = float(self.settings["sigma"])
            if sigma != self.enhancement_sigma:
                fine = smooth(self.source, self.channels.shape, sigma, first_field=1)
                coarse = smooth(
                    self.source, self.channels.shape, sigma * 2, first_field=1
                )
                self.enhancement_shader.set_resource(1, fine)
                self.enhancement_shader.set_resource(2, coarse)
                self.fine.destroy()
                self.coarse.destroy()
                self.fine = fine
                self.coarse = coarse
                self.enhancement_sigma = sigma
            self.enhancement_shader.set_constant(
                "strength", float(self.settings["strength"])
            )
            self.enhancement_shader.dispatch((self.channels.size + 255) // 256)
            result = self.enhanced
        elif self.mode == Analysis.CORRELATION:
            result = analyze(
                self.source,
                dimensions,
                float(self.settings["sigma"]),
                maximum_brightfield=float(self.settings["maximum_brightfield"]),
            )
        elif self.mode == Analysis.DISTANCE:
            result, profiles = distance_field(
                self.source,
                dimensions,
                float(self.settings["sigma"]),
                minimum_signal=float(self.settings["minimum_signal"]),
            )
            self.distance_profiles = np.frombuffer(
                self.renderer.device.queue.read_buffer(profiles),
                dtype=np.float32,
            ).reshape(-1, 4)
            occupied = np.flatnonzero(self.distance_profiles[:, 2])
            self.distance_profiles = self.distance_profiles[
                : occupied[-1] + 1 if len(occupied) else 0
            ]
        else:
            result, profiles = unwrap(
                self.source,
                dimensions,
                (
                    float(self.settings["center_x"]),
                    float(self.settings["center_y"]),
                ),
                float(self.settings["maximum_radius"]),
            )
            self.radial_profiles = np.frombuffer(
                self.renderer.device.queue.read_buffer(profiles),
                dtype=np.float32,
            ).reshape(self.height, 4)
            occupied = np.flatnonzero(self.radial_profiles[:, 2])
            self.radial_profiles = self.radial_profiles[
                : occupied[-1] + 1 if len(occupied) else 0
            ]
        if self.mode in (Analysis.ENHANCEMENT, Analysis.POLAR):
            self.processed_shader.set_resource(0, result)
            self.processed_shader.dispatch(
                (self.width + 15) // 16, (self.height + 15) // 16
            )
            self.geometries[1].grid = self.processed_texture
            self.analysis_shader = None
        else:
            self.analysis_shader = create_shader(
                "display.wesl",
                dimensions,
                entry_point=(
                    "correlation_overlay"
                    if self.mode == Analysis.CORRELATION
                    else "distance_overlay"
                ),
            )
            self.analysis_shader.set_resource(0, result)
            self.analysis_shader.set_resource(1, self.original_texture)
            self.analysis_shader.set_resource(2, self.analysis_texture)
            self.analysis_shader.set_resource(3, self.display_parameters)
            self.geometries[1].grid = self.analysis_texture
        self.settings["process"] = False
        self.settings["display"] = True

    def _update_colors(self) -> None:
        displayed_weights = self.weights.copy()
        displayed_weights[:3] *= self.visible
        for shader, parameters in (
            (self.original_shader, self.original_weights),
            (self.processed_shader, self.processed_weights),
        ):
            self.renderer.device.queue.write_buffer(parameters, 0, displayed_weights)
            shader.dispatch((self.width + 15) // 16, (self.height + 15) // 16)
        self.settings["color"] = False
        self.settings["display"] = True

    def _update_display(self) -> None:
        parameters = np.array(
            [
                self.settings["center_x"],
                self.settings["center_y"],
                self.settings["maximum_radius"],
                self.settings["opacity"],
                self.settings["spacing"],
                0,
                0,
                0,
            ],
            dtype=np.float32,
        )
        self.renderer.device.queue.write_buffer(self.display_parameters, 0, parameters)
        if self.analysis_shader is not None:
            self.analysis_shader.dispatch(
                (self.width + 15) // 16, (self.height + 15) // 16
            )
        if self.mode == Analysis.POLAR:
            self.guide_shader.dispatch(
                (self.width + 15) // 16, (self.height + 15) // 16
            )
            self.geometries[0].grid = self.guide_texture
        else:
            self.geometries[0].grid = self.original_texture
        self.settings["display"] = False

    def draw_frame(self) -> None:
        if self.settings["process"]:
            self._update_analysis()
        if self.settings["color"]:
            self._update_colors()
        if self.settings["display"]:
            self._update_display()
        canvas_width, canvas_height = self.canvas.get_logical_size()
        panel_width = (canvas_width - 336) / 2
        if panel_width - 8 > 0 and canvas_height - 84 > 0:
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
