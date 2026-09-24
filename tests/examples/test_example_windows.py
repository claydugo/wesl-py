from __future__ import annotations

import asyncio
import logging
import os
import sys
from importlib import import_module
from typing import TYPE_CHECKING

import pytest

numpy = pytest.importorskip("numpy")
glfw = pytest.importorskip("glfw")
pytest.importorskip("pygfx")
imgui = pytest.importorskip("imgui_bundle.imgui")
loop = import_module("rendercanvas.glfw").loop

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(
        sys.platform == "linux"
        and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        reason="requires a window server",
    ),
]


if TYPE_CHECKING:
    from collections.abc import Iterator

    from rendercanvas.glfw import GlfwRenderCanvas


@pytest.fixture
def canvas() -> Iterator[GlfwRenderCanvas]:
    canvas = import_module("rendercanvas.glfw").RenderCanvas()
    try:
        if sys.platform == "linux" and glfw.get_platform() == glfw.PLATFORM_WAYLAND:
            pytest.skip("requires X11 for native cursor positioning")
        yield canvas
    finally:
        canvas.close()


def draw(
    canvas: GlfwRenderCanvas, render_loop: asyncio.Runner, event: dict | None = None
) -> None:
    rendered = render_loop.get_loop().create_future()
    delivered = event is None

    def observe(received: dict) -> None:
        nonlocal delivered
        if received is event:
            delivered = True
        elif (
            received["event_type"] == "before_draw"
            and delivered
            and not rendered.done()
        ):
            rendered.set_result(None)

    canvas.add_event_handler(observe, "before_draw", order=-100)
    if event is not None:
        window = canvas._window  # noqa: SLF001
        window_width, window_height = glfw.get_window_size(window)
        width, height = canvas.get_logical_size()
        glfw.set_cursor_pos(
            window,
            event["x"] * window_width / width,
            event["y"] * window_height / height,
        )
        canvas.add_event_handler(observe, event["event_type"], order=-100)
    try:
        if event is not None:
            canvas.submit_event(event)
        canvas.request_draw()
        render_loop.run(asyncio.wait_for(rendered, timeout=5))
    finally:
        canvas.remove_event_handler(observe, "before_draw")
        if event is not None:
            canvas.remove_event_handler(observe, event["event_type"])


def test_native_pointer_coordinates(
    canvas: GlfwRenderCanvas, caplog: pytest.LogCaptureFixture
) -> None:
    channels = numpy.full((3, 19, 37), 0.25, dtype=numpy.float32)
    colors = numpy.ones((3, 256, 4), dtype=numpy.float32)
    viewer = import_module("examples.multiscale.viewer").Viewer(
        canvas, channels, colors, ["Brightfield", "GFP", "RFP"]
    )
    with asyncio.Runner() as render_loop:
        render_loop.get_loop().create_task(loop.run_async())
        try:
            for dimensions in ((1600, 960), (1024, 768)):
                canvas.set_logical_size(*dimensions)
                for _ in range(3):
                    draw(canvas, render_loop)
                for channel, y in ((0, 221), (1, 285), (2, 349)):
                    previous = viewer.visible[channel]
                    draw(
                        canvas,
                        render_loop,
                        {
                            "event_type": "pointer_move",
                            "x": 36,
                            "y": y,
                            "buttons": (),
                            "modifiers": (),
                        },
                    )
                    numpy.testing.assert_allclose(
                        tuple(imgui.get_io().mouse_pos), (36, y)
                    )
                    for event_type in ("pointer_down", "pointer_up"):
                        draw(
                            canvas,
                            render_loop,
                            {
                                "event_type": event_type,
                                "x": 36,
                                "y": y,
                                "button": 1,
                                "buttons": (1,) if event_type == "pointer_down" else (),
                                "modifiers": (),
                            },
                        )
                    assert viewer.visible[channel] is not previous
        finally:
            canvas.close()
            loop.stop(force=True)
            render_loop.run(asyncio.sleep(0))
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_sdf_pointer_controls(
    canvas: GlfwRenderCanvas, caplog: pytest.LogCaptureFixture
) -> None:
    viewer = import_module("examples.sdf.viewer").Viewer(canvas)
    with asyncio.Runner() as render_loop:
        render_loop.get_loop().create_task(loop.run_async())
        try:
            for dimensions in ((1440, 900), (1024, 768)):
                canvas.set_logical_size(*dimensions)
                for _ in range(3):
                    draw(canvas, render_loop)
                for attribute in ("cutout", "paused"):
                    previous = getattr(viewer, attribute)
                    y = 172 if attribute == "cutout" else 310 if viewer.cutout else 278
                    draw(
                        canvas,
                        render_loop,
                        {
                            "event_type": "pointer_move",
                            "x": 36,
                            "y": y,
                            "buttons": (),
                            "modifiers": (),
                        },
                    )
                    for event_type in ("pointer_down", "pointer_up"):
                        draw(
                            canvas,
                            render_loop,
                            {
                                "event_type": event_type,
                                "x": 36,
                                "y": y,
                                "button": 1,
                                "buttons": (1,) if event_type == "pointer_down" else (),
                                "modifiers": (),
                            },
                        )
                    assert getattr(viewer, attribute) is not previous
        finally:
            canvas.close()
            loop.stop(force=True)
            render_loop.run(asyncio.sleep(0))
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
