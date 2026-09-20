from __future__ import annotations

import asyncio
import logging
import os
import runpy
import sys
from importlib import import_module
from typing import TYPE_CHECKING

import pytest

numpy = pytest.importorskip("numpy")
glfw = pytest.importorskip("glfw")
pytest.importorskip("pygfx")
imgui = pytest.importorskip("imgui_bundle.imgui")
common = import_module("examples.common")
loop = import_module("rendercanvas.glfw").loop


if TYPE_CHECKING:
    from rendercanvas import BaseRenderCanvas


def draw(
    canvas: BaseRenderCanvas, render_loop: asyncio.Runner, event: dict | None = None
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


@pytest.mark.gpu
@pytest.mark.skipif(
    sys.platform == "linux"
    and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="requires a window server",
)
def test_native_pointer_coordinates(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    channels = numpy.full((3, 19, 37), 0.25, dtype=numpy.float32)
    colors = numpy.ones((3, 256, 4), dtype=numpy.float32)
    labels = ["Brightfield", "GFP", "RFP"]
    monkeypatch.setattr(common, "load_colony", lambda: (channels, colors, labels))
    monkeypatch.setattr(loop, "run", lambda: None)
    monkeypatch.setattr(sys, "argv", ["examples.multiscale"])
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
    viewer = runpy.run_module("examples.multiscale", run_name="__main__")
    canvas = viewer["canvas"]
    glfw.poll_events()
    monkeypatch.setattr(glfw, "poll_events", lambda: None)
    imgui.get_io().config_input_trickle_event_queue = False
    with asyncio.Runner() as render_loop:
        render_loop.get_loop().create_task(loop.run_async())
        try:
            for dimensions in (None, (1024, 768)):
                if dimensions is not None:
                    canvas.set_logical_size(*dimensions)
                for _ in range(3):
                    draw(canvas, render_loop)
                for channel, label in enumerate(labels):
                    lower, upper = rectangles[label]
                    x = lower[0] + 8
                    y = (lower[1] + upper[1]) / 2
                    previous = viewer["visible"][channel]
                    draw(
                        canvas,
                        render_loop,
                        {
                            "event_type": "pointer_move",
                            "x": x,
                            "y": y,
                            "buttons": (),
                            "modifiers": (),
                        },
                    )
                    numpy.testing.assert_allclose(
                        tuple(imgui.get_io().mouse_pos), (x, y)
                    )
                    for event_type in ("pointer_down", "pointer_up"):
                        draw(
                            canvas,
                            render_loop,
                            {
                                "event_type": event_type,
                                "x": x,
                                "y": y,
                                "button": 1,
                                "buttons": (1,) if event_type == "pointer_down" else (),
                                "modifiers": (),
                            },
                        )
                    assert viewer["visible"][channel] is not previous
        finally:
            canvas.close()
            loop.stop(force=True)
            render_loop.run(asyncio.sleep(0))
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.gpu
@pytest.mark.skipif(
    sys.platform == "linux"
    and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="requires a window server",
)
def test_sdf_pointer_controls(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rendercanvas = import_module("rendercanvas.glfw")
    viewer_module = import_module("examples.sdf.viewer")
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
    canvas = rendercanvas.RenderCanvas()
    canvas.set_logical_size(1440, 900)
    viewer = viewer_module.Viewer(canvas)
    glfw.poll_events()
    monkeypatch.setattr(glfw, "poll_events", lambda: None)
    imgui.get_io().config_input_trickle_event_queue = False
    with asyncio.Runner() as render_loop:
        render_loop.get_loop().create_task(loop.run_async())
        try:
            for dimensions in (None, (1024, 768)):
                if dimensions is not None:
                    canvas.set_logical_size(*dimensions)
                for _ in range(3):
                    draw(canvas, render_loop)
                for label in ("Cut a tunnel", "Pause"):
                    lower, upper = rectangles[label]
                    previous = (viewer.cutout, viewer.paused)
                    x = lower[0] + 8
                    y = (lower[1] + upper[1]) / 2
                    draw(
                        canvas,
                        render_loop,
                        {
                            "event_type": "pointer_move",
                            "x": x,
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
                                "x": x,
                                "y": y,
                                "button": 1,
                                "buttons": (1,) if event_type == "pointer_down" else (),
                                "modifiers": (),
                            },
                        )
                    if label == "Cut a tunnel":
                        assert (viewer.cutout, viewer.paused) == (
                            not previous[0],
                            previous[1],
                        )
                    else:
                        assert (viewer.cutout, viewer.paused) == (
                            previous[0],
                            not previous[1],
                        )
        finally:
            canvas.close()
            loop.stop(force=True)
            render_loop.run(asyncio.sleep(0))
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
