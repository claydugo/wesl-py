import logging
from importlib import import_module

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("wgpu")
pytest.importorskip("imgui_bundle")


@pytest.mark.gpu
def test_optimizer_viewer(caplog: pytest.LogCaptureFixture) -> None:
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1440, 720))
    viewer = import_module("examples.optimizers.viewer").Viewer(canvas)
    try:
        renderer = viewer.renderer
        viewer.paused = True
        parameter_count = renderer.layout["parameter_count"]
        first_moments = [np.zeros(parameter_count) for _ in renderer.rules]
        second_moments = [np.zeros(parameter_count) for _ in renderer.rules]
        for step in range(1, 4):
            before = [renderer.read(buffer).copy() for buffer in renderer.parameters]
            renderer.train(1)
            for index, rule in enumerate(renderer.rules):
                gradient = (
                    renderer.read(renderer.gradients[index])
                    .reshape(-1, parameter_count)
                    .mean(0, dtype=np.float64)
                )
                if index == 0:
                    change = rule.learning_rate * gradient
                elif index == 1:
                    first_moments[index] = 0.9 * first_moments[index] + gradient
                    change = rule.learning_rate * first_moments[index]
                else:
                    first_moments[index] = 0.9 * first_moments[index] + 0.1 * gradient
                    second_moments[index] = (
                        0.999 * second_moments[index] + 0.001 * gradient**2
                    )
                    change = (
                        rule.learning_rate
                        * first_moments[index]
                        / (1 - 0.9**step)
                        / (np.sqrt(second_moments[index] / (1 - 0.999**step)) + 1e-8)
                    )
                assert np.abs(change).max() > 1e-4
                np.testing.assert_allclose(
                    renderer.read(renderer.parameters[index]),
                    before[index] - change,
                    atol=1e-6,
                )
        viewer.paused = False
        for _ in range(300):
            canvas.draw()
        losses = [history[-1, 0] for history in viewer.histories]
        assert losses[2] < losses[0]
        assert viewer.perfect_steps[2] is not None
        assert viewer.error is None
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()
