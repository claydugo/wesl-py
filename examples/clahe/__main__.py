import argparse
from pathlib import Path

import imageio.v3 as imageio
import numpy
import pygfx
from imgui_bundle import imgui
from rendercanvas.offscreen import RenderCanvas as OffscreenRenderCanvas
from wgpu.utils.imgui import ImguiRenderer

from examples.clahe.compute import equalize
from examples.common import composite, load_colony

parser = argparse.ArgumentParser(
    description="Explore adaptive contrast in microscopy channels."
)
parser.add_argument(
    "--screenshot", type=Path, help="Save a PNG without opening a window."
)
arguments = parser.parse_args()
if arguments.screenshot:
    canvas = OffscreenRenderCanvas(size=(1600, 960))
else:
    from rendercanvas.glfw import RenderCanvas, loop

    canvas = RenderCanvas(title="WESL | Adaptive local contrast")
    canvas.set_logical_size(1600, 960)
renderer = pygfx.WgpuRenderer(canvas)
channels, colors, labels = load_colony()
_, height, width = channels.shape
weights = numpy.array([0.12, 1.5, 1.5, 0], dtype=numpy.float32)
visible = [True, True, True]
settings = {"tile_size": 128, "clip_limit": 2.0, "process": False, "color": False}
source, histograms, lookup_tables, output = equalize(
    renderer.device, channels, 128, 2.0
)
original_texture, original_shader, original_weights = composite(
    renderer.device, source, colors, weights, (width, height)
)
processed_texture, processed_shader, processed_weights = composite(
    renderer.device, output, colors, weights, (width, height)
)

scenes = []
cameras = []
viewports = []
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
    scenes.append(scene)
    cameras.append(camera)
    viewports.append(pygfx.Viewport(renderer))
controller = pygfx.PanZoomController(cameras[0])
controller.add_camera(cameras[1])
controller.register_events(viewports[0])
controller.register_events(viewports[1])


def draw_controls() -> None:
    canvas_width, canvas_height = canvas.get_logical_size()
    imgui.set_next_window_pos((16, 16), imgui.Cond_.always)
    imgui.set_next_window_size((288, canvas_height - 32), imgui.Cond_.always)
    imgui.begin(
        "Adaptive local contrast",
        flags=imgui.WindowFlags_.no_move
        | imgui.WindowFlags_.no_resize
        | imgui.WindowFlags_.no_collapse,
    )
    imgui.text_wrapped(
        "Reveal dim structures with contrast limits applied "
        "independently to each channel."
    )
    imgui.spacing()
    changed, settings["tile_size"] = imgui.slider_int(
        "Tile size", int(settings["tile_size"]), 16, 256, "%d px"
    )
    if changed:
        settings["process"] = True
    changed, settings["clip_limit"] = imgui.slider_float(
        "Clip limit", float(settings["clip_limit"]), 0.5, 8.0
    )
    if changed:
        settings["process"] = True
    imgui.separator()
    imgui.text("Channels")
    for channel, label in enumerate(labels):
        imgui.push_id(channel)
        changed, visible[channel] = imgui.checkbox(label, visible[channel])
        if changed:
            settings["color"] = True
        changed, weights[channel] = imgui.slider_float(
            "Gain", float(weights[channel]), 0.0, 3.0
        )
        if changed:
            settings["color"] = True
        imgui.pop_id()
    imgui.separator()
    imgui.text_wrapped("Drag either image to pan. Scroll to zoom both views.")
    if imgui.button("Reset view"):
        for camera, scene in zip(cameras, scenes, strict=True):
            camera.show_object(scene.children[1], match_aspect=True)
    imgui.spacing()
    imgui.text_wrapped(
        "Each tile builds a contrast curve. Interpolation joins the curves "
        "across tile boundaries."
    )
    imgui.end()
    panel_width = (canvas_width - 336) / 2
    for index, title in enumerate(("Original composite", "Locally enhanced")):
        imgui.set_next_window_pos((320 + index * panel_width, 16), imgui.Cond_.always)
        imgui.set_next_window_size((panel_width - 8, 44), imgui.Cond_.always)
        imgui.begin(
            title, flags=imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_inputs
        )
        imgui.text(title)
        imgui.end()


gui_renderer = ImguiRenderer(renderer.device, canvas)
imgui.style_colors_dark()
imgui.get_io().font_default = imgui.get_io().fonts.add_font_default_vector()
imgui.get_style().font_size_base = 16
imgui.get_style().frame_padding = imgui.ImVec2(6, 4)
imgui.get_style().item_spacing = imgui.ImVec2(8, 8)
gui_renderer.set_gui(draw_controls)


def draw_frame() -> None:
    if settings["process"]:
        _, _, _, result = equalize(
            renderer.device,
            channels,
            int(settings["tile_size"]),
            float(settings["clip_limit"]),
        )
        processed_shader.set_resource(0, result)
        processed_shader.dispatch((width + 15) // 16, (height + 15) // 16)
        settings["process"] = False
    if settings["color"]:
        displayed_weights = weights.copy()
        displayed_weights[:3] *= visible
        for shader, parameters in (
            (original_shader, original_weights),
            (processed_shader, processed_weights),
        ):
            renderer.device.queue.write_buffer(parameters, 0, displayed_weights)
            shader.dispatch((width + 15) // 16, (height + 15) // 16)
        settings["color"] = False
    canvas_width, canvas_height = canvas.get_logical_size()
    panel_width = (canvas_width - 336) / 2
    for index, (viewport, scene, camera) in enumerate(
        zip(viewports, scenes, cameras, strict=True)
    ):
        viewport.rect = (
            320 + index * panel_width,
            68,
            panel_width - 8,
            canvas_height - 84,
        )
        viewport.render(scene, camera)
    renderer.flush()
    gui_renderer.render()
    canvas.request_draw()


canvas.request_draw(draw_frame)
if isinstance(canvas, OffscreenRenderCanvas):
    for _ in range(3):
        frame = canvas.draw()
    imageio.imwrite(arguments.screenshot, numpy.asarray(frame))
else:
    loop.run()
