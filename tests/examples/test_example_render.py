import logging
from importlib import import_module

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pygfx")
pytest.importorskip("imgui_bundle")


@pytest.mark.gpu
def test_enhancement_reuses_buffers() -> None:
    viewer_module = import_module("examples.multiscale.viewer")
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1600, 960))
    channels = np.random.default_rng(42).random((3, 19, 37), dtype=np.float32)
    colors = np.zeros((3, 256, 4), dtype=np.float32)
    colors[:, :, 3] = 1
    try:
        viewer = viewer_module.Viewer(
            canvas, channels, colors, ["Brightfield", "GFP", "RFP"]
        )
        source, fine, coarse, output = (
            viewer.source,
            viewer.fine,
            viewer.coarse,
            viewer.enhanced,
        )
        viewer.gui_renderer.render()
        prepared = np.asarray(canvas.draw()).copy()
        np.testing.assert_array_equal(prepared, np.asarray(canvas.draw()))
        viewer.settings["strength"] = 0.0
        viewer.settings["process"] = True
        canvas.draw()
        assert viewer.fine is fine
        assert viewer.coarse is coarse
        actual = np.frombuffer(
            viewer.renderer.device.queue.read_buffer(output), dtype=np.float32
        ).reshape(channels.shape)
        np.testing.assert_array_equal(actual, channels)
        viewer.settings["sigma"] = 0.7
        viewer.settings["strength"] = 1.5
        viewer.settings["process"] = True
        canvas.draw()
        assert viewer.source is source
        assert viewer.enhanced is output
        assert viewer.fine is not fine
        assert viewer.coarse is not coarse
        expected_buffers = import_module("examples.multiscale.compute").enhance(
            channels, 0.7, 1.5
        )
        try:
            np.testing.assert_array_equal(
                np.frombuffer(
                    viewer.renderer.device.queue.read_buffer(output), dtype=np.float32
                ),
                np.frombuffer(
                    viewer.renderer.device.queue.read_buffer(expected_buffers[-1]),
                    dtype=np.float32,
                ),
            )
        finally:
            for buffer in expected_buffers:
                buffer.destroy()
    finally:
        canvas.close()


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
    viewer_module = import_module("examples.multiscale.viewer")
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1600, 960))
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
        left, top, width, height = map(int, viewer.viewports[1].rect)
        assert before[top + height // 2, left + width // 2, :3].min() > 200
        viewer.weights[1:3] = 0
        viewer.settings["color"] = True
        after = np.asarray(canvas.draw())
        np.testing.assert_array_equal(
            before[top : top + height, left : left + width],
            after[top : top + height, left : left + width],
        )
        left, top, width, height = map(int, viewer.viewports[0].rect)
        assert before[top + height // 2, left + width // 2, :3].sum() > 0
        np.testing.assert_array_equal(
            after[top + height // 2, left + width // 2, :3], [0, 0, 0]
        )
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()
