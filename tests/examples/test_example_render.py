import logging
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")
imageio = pytest.importorskip("imageio.v3")
pytest.importorskip("pygfx")
pytest.importorskip("imgui_bundle")


@pytest.mark.gpu
def test_offscreen_render(caplog: pytest.LogCaptureFixture) -> None:
    channels = numpy.zeros((3, 19, 37), dtype=numpy.float32)
    channels[1, 5:14, 10:27] = 0.2
    channels[1, 9, 18] = 1
    colors = numpy.zeros((3, 256, 4), dtype=numpy.float32)
    colors[:, :, 3] = 1
    colors[1, :, 1] = numpy.linspace(0, 1, 256)
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1600, 960))
    viewer_module = import_module("examples.multiscale.viewer")
    try:
        viewer = viewer_module.Viewer(
            canvas, channels, colors, ["Brightfield", "GFP", "RFP"]
        )
        for _ in range(3):
            image = numpy.asarray(canvas.draw())
        assert numpy.any(image[68:944, 320:944] != image[68:944, 952:1576])
        viewer.settings["strength"] = 0.0
        viewer.settings["process"] = True
        image = numpy.asarray(canvas.draw())
        numpy.testing.assert_allclose(
            image[68:944, 320:944], image[68:944, 952:1576], rtol=0, atol=1
        )
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()


@pytest.mark.gpu
def test_multiscale_cli(tmp_path: Path, pytestconfig: pytest.Config) -> None:
    if not pytestconfig.getoption("--image"):
        pytest.skip("requires --image to load the sample TIFF")
    screenshot = tmp_path / "viewer.png"
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "examples.multiscale", "--screenshot", str(screenshot)],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    image = imageio.imread(screenshot)
    assert image.shape == (960, 1600, 4)
    assert numpy.any(image[68:944, 320:944] != image[68:944, 952:1576])
