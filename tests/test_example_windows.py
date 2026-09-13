# ruff: noqa: SLF001

import os
import runpy
import sys
from importlib import import_module

import pytest

numpy = pytest.importorskip("numpy")
glfw = pytest.importorskip("glfw")
pytest.importorskip("pygfx")
imgui = pytest.importorskip("imgui_bundle.imgui")
common = import_module("examples.common")
loop = import_module("rendercanvas.glfw").loop


@pytest.mark.gpu
@pytest.mark.skipif(
    sys.platform == "linux"
    and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="requires a window server",
)
@pytest.mark.parametrize("module", ["examples.multiscale", "examples.clahe"])
def test_native_pointer_coordinates(
    module: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    channels = numpy.full((3, 19, 37), 0.25, dtype=numpy.float32)
    colors = numpy.ones((3, 256, 4), dtype=numpy.float32)
    labels = ["Brightfield", "GFP", "RFP"]
    monkeypatch.setattr(common, "load_colony", lambda: (channels, colors, labels))
    monkeypatch.setattr(loop, "run", lambda: None)
    monkeypatch.setattr(sys, "argv", [module])
    rectangles = {}
    checkbox = imgui.checkbox

    def record_checkbox(label: str, value: bool) -> tuple[bool, bool]:  # noqa: FBT001
        result = checkbox(label, value)
        rectangles[label] = (
            tuple(imgui.get_item_rect_min()),
            tuple(imgui.get_item_rect_max()),
        )
        return result

    monkeypatch.setattr(imgui, "checkbox", record_checkbox)
    viewer = runpy.run_module(module, run_name="__main__")
    canvas = viewer["canvas"]
    try:
        for dimensions in (None, (1024, 768)):
            if dimensions is not None:
                canvas.set_logical_size(*dimensions)
            for _ in range(3):
                glfw.poll_events()
                canvas._events.flush()
                canvas.force_draw()
            canvas._on_cursor_enter(canvas._window, entered=True)
            window_width, window_height = glfw.get_window_size(canvas._window)
            logical_width, logical_height = canvas.get_logical_size()
            for channel, label in enumerate(labels):
                lower, upper = rectangles[label]
                x = lower[0] + 8
                y = (lower[1] + upper[1]) / 2
                previous = viewer["visible"][channel]
                canvas._on_cursor_pos(
                    canvas._window,
                    x * window_width / logical_width,
                    y * window_height / logical_height,
                )
                canvas._events.flush()
                canvas.force_draw()
                numpy.testing.assert_allclose(tuple(imgui.get_io().mouse_pos), (x, y))
                for action in (glfw.PRESS, glfw.RELEASE):
                    canvas._on_mouse_button(
                        canvas._window, glfw.MOUSE_BUTTON_LEFT, action, 0
                    )
                    canvas._events.flush()
                    canvas.force_draw()
                assert viewer["visible"][channel] is not previous
    finally:
        canvas.close()
