import logging
import runpy
import sys
from importlib import import_module
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")
imageio = pytest.importorskip("imageio.v3")
pytest.importorskip("pygfx")
pytest.importorskip("imgui_bundle")
common = import_module("examples.common")


@pytest.mark.gpu
def test_offscreen_render(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    channels = numpy.full((3, 19, 37), 0.25, dtype=numpy.float32)
    colors = numpy.ones((3, 256, 4), dtype=numpy.float32)
    labels = ["Brightfield", "GFP", "RFP"]
    monkeypatch.setattr(common, "load_colony", lambda: (channels, colors, labels))
    screenshot = tmp_path / "viewer.png"
    monkeypatch.setattr(
        sys, "argv", ["examples.multiscale", "--screenshot", str(screenshot)]
    )
    viewer = runpy.run_module("examples.multiscale", run_name="__main__")
    try:
        viewer["draw_frame"]()
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
        image = imageio.imread(screenshot)
        assert image.shape == (960, 1600, 4)
        assert numpy.ptp(image[:, :, :3]) > 0
    finally:
        viewer["canvas"].close()
