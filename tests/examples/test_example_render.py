import logging
from importlib import import_module

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pygfx")
pytest.importorskip("imgui_bundle")


@pytest.mark.gpu
def test_multiscale_analysis_views(caplog: pytest.LogCaptureFixture) -> None:
    coordinates_y, coordinates_x = np.indices((19, 37), dtype=np.float32)
    channels = np.array(
        [np.full((19, 37), 0.1), coordinates_x / 37, coordinates_y / 19],
        dtype=np.float32,
    )
    colors = np.zeros((3, 256, 4), dtype=np.float32)
    colors[:, :, 3] = 1
    colors[1, :, 1] = np.linspace(0, 1, 256)
    colors[2, :, 0] = np.linspace(0, 1, 256)
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1600, 960))
    viewer_module = import_module("examples.multiscale.viewer")
    try:
        viewer = viewer_module.Viewer(
            canvas, channels, colors, ["Brightfield", "GFP", "RFP"]
        )
        viewer.mode = viewer_module.Analysis.DISTANCE
        viewer.settings["minimum_signal"] = 0.0
        viewer.settings["process"] = True
        canvas.draw()
        assert viewer.distance_profiles is not None
        assert viewer.distance_profiles[:, 2].sum() == 19 * 37
        viewer.settings["minimum_signal"] = 2.0
        viewer.settings["process"] = True
        canvas.draw()
        assert viewer.distance_profiles.shape == (0, 4)
        viewer.mode = viewer_module.Analysis.POLAR
        viewer.settings["maximum_radius"] = 8.0
        viewer.settings["process"] = True
        canvas.draw()
        assert viewer.radial_profiles is not None
        expected_profiles = np.empty((19, 4), dtype=np.float32)
        expected_profiles[:, 0] = 18 / 37
        expected_profiles[:, 1] = 9 / 19
        expected_profiles[:, 2] = 37
        expected_profiles[:, 3] = np.linspace(0, 8, 19)
        np.testing.assert_allclose(
            viewer.radial_profiles, expected_profiles, rtol=1e-6, atol=1e-6
        )
        viewer.mode = viewer_module.Analysis.CORRELATION
        viewer.settings["opacity"] = 1.0
        viewer.settings["maximum_brightfield"] = 0.9
        viewer.settings["process"] = True
        before = np.asarray(canvas.draw()).copy()
        viewer.weights[1:3] = 0
        viewer.settings["color"] = True
        after = np.asarray(canvas.draw())
        np.testing.assert_array_equal(before[68:944, 952:1576], after[68:944, 952:1576])
        assert before[500, 600, :3].sum() > 0
        np.testing.assert_array_equal(after[500, 600, :3], [0, 0, 0])
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()
