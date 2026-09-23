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
def test_multiscale_analysis_views(caplog: pytest.LogCaptureFixture) -> None:
    coordinates_y, coordinates_x = numpy.indices((19, 37), dtype=numpy.float32)
    channels = numpy.array(
        [numpy.full((19, 37), 0.1), coordinates_x / 37, coordinates_y / 19],
        dtype=numpy.float32,
    )
    colors = numpy.zeros((3, 256, 4), dtype=numpy.float32)
    colors[:, :, 3] = 1
    colors[1, :, 1] = numpy.linspace(0, 1, 256)
    colors[2, :, 0] = numpy.linspace(0, 1, 256)
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1600, 960))
    viewer_module = import_module("examples.multiscale.viewer")
    try:
        viewer = viewer_module.Viewer(
            canvas, channels, colors, ["Brightfield", "GFP", "RFP"]
        )
        for mode in viewer.modes:
            viewer.mode = mode
            viewer.settings["process"] = True
            for _ in range(2):
                image = numpy.asarray(canvas.draw())
            assert numpy.any(image[68:944, 320:944] != image[68:944, 952:1576])
        assert viewer.radial_profiles is not None
        assert viewer.distance_profiles is not None
        assert viewer.radial_profiles.shape == (19, 4)
        assert viewer.distance_profiles.shape[1] == 4  # noqa: PLR2004
        assert viewer.distance_profiles[:, 2].sum() > 0
        viewer.mode = viewer_module.Analysis.DISTANCE
        viewer.settings["minimum_signal"] = 1.0
        viewer.settings["process"] = True
        canvas.draw()
        assert viewer.distance_profiles[:, 2].sum() < 19 * 37
        viewer.mode = viewer_module.Analysis.CORRELATION
        viewer.settings["opacity"] = 1.0
        viewer.settings["maximum_brightfield"] = 0.9
        viewer.settings["process"] = True
        before = numpy.asarray(canvas.draw()).copy()
        viewer.weights[1:3] = 0
        viewer.settings["color"] = True
        after = numpy.asarray(canvas.draw())
        numpy.testing.assert_array_equal(
            before[68:944, 952:1576], after[68:944, 952:1576]
        )
        assert numpy.any(before[68:944, 320:944] != after[68:944, 320:944])
        viewer.mode = viewer_module.Analysis.ENHANCEMENT
        viewer.settings["process"] = True
        canvas.draw()
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()


@pytest.mark.gpu
def test_polar_profiles_omit_unsampled_rings() -> None:
    channels = numpy.full((3, 32, 32), 0.4, dtype=numpy.float32)
    channels[2] = 0.7
    colors = numpy.ones((3, 256, 4), dtype=numpy.float32)
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1600, 960))
    viewer_module = import_module("examples.multiscale.viewer")
    try:
        viewer = viewer_module.Viewer(
            canvas, channels, colors, ["Brightfield", "GFP", "RFP"]
        )
        viewer.mode = viewer_module.Analysis.POLAR
        viewer.settings["maximum_radius"] = 40.0
        viewer.settings["process"] = True
        canvas.draw()
        assert viewer.radial_profiles is not None
        assert viewer.radial_profiles.shape == (17, 4)
        numpy.testing.assert_allclose(
            viewer.radial_profiles[:, :2], numpy.broadcast_to([0.4, 0.7], (17, 2))
        )
        assert numpy.all(viewer.radial_profiles[:, 2] > 0)
        assert viewer.radial_profiles[-1, 3] == pytest.approx(40 * 16 / 31)
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
