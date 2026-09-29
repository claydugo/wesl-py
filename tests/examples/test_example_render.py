import logging
from importlib import import_module

import pytest

numpy = pytest.importorskip("numpy")
pytest.importorskip("pygfx")
pytest.importorskip("imgui_bundle")


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
