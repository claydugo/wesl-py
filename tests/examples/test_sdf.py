import logging
from importlib import import_module
from pathlib import Path

import pytest
import wesl

np = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")
get_default_device = import_module("wgpu.utils").get_default_device


@pytest.mark.gpu
@pytest.mark.parametrize("cutout", [False, True], ids=["solid", "cutout"])
def test_particle_collisions(*, cutout: bool) -> None:
    directory = Path(__file__).parents[2] / "examples"
    device = get_default_device()
    parameters = np.zeros((7, 4), dtype=np.float32)
    parameters[0] = (640, 480, 1, 1 / 60)
    parameters[1] = (0.35, 0.48, 0.7, 0)
    parameters[6] = (0.55, 5, 0, 0)
    particles = np.array(
        [
            [2, -1.24, 0, 5, 0, -1, 0, 0.035],
            [0, 2.12, 0, 5, 0, -1, 0, 0.035],
        ],
        dtype=np.float32,
    )
    module = device.create_shader_module(
        code=wesl.compile_file(
            directory / "sdf/shaders/simulate.wesl",
            root_directory=directory.parent,
            options=wesl.CompileOptions(
                visibility=True, features=wesl.Features(flags={"cutout": cutout})
            ),
        ).wgsl
    )
    pipeline = device.create_compute_pipeline(
        layout="auto", compute={"module": module, "entry_point": "main"}
    )
    output = device.create_buffer_with_data(
        data=particles, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
    )
    bindings = device.create_bind_group(
        layout=pipeline.get_bind_group_layout(0),
        entries=[
            {
                "binding": 0,
                "resource": {
                    "buffer": device.create_buffer_with_data(
                        data=parameters, usage=wgpu.BufferUsage.UNIFORM
                    )
                },
            },
            {"binding": 1, "resource": {"buffer": output}},
        ],
    )
    encoder = device.create_command_encoder()
    compute_pass = encoder.begin_compute_pass()
    compute_pass.set_pipeline(pipeline)
    compute_pass.set_bind_group(0, bindings)
    compute_pass.dispatch_workgroups(1)
    compute_pass.end()
    device.queue.submit([encoder.finish()])
    result = np.frombuffer(device.queue.read_buffer(output), dtype=np.float32)
    result = result.reshape(2, 8)
    assert np.isfinite(result).all()
    assert result[0, 1] >= -1.215001
    assert result[0, 5] > 0
    if cutout:
        assert result[1, 1] < 2.12
        assert result[1, 5] < -1
    else:
        assert result[1, 1] >= 2.135
        assert result[1, 5] > 0


@pytest.mark.gpu
def test_sdf_viewer(caplog: pytest.LogCaptureFixture) -> None:
    pytest.importorskip("imgui_bundle")
    canvas_module = import_module("rendercanvas.offscreen")
    viewer_module = import_module("examples.sdf.viewer")
    canvas = canvas_module.RenderCanvas(size=(800, 600))
    viewer = viewer_module.Viewer(canvas)
    try:
        viewer.paused = True
        original = np.asarray(canvas.draw()).copy()
        initialized = np.frombuffer(
            viewer.renderer.device.queue.read_buffer(viewer.renderer.particles),
            dtype=np.float32,
        ).copy()
        viewer.cutout = False
        filled = np.asarray(canvas.draw()).copy()
        assert np.count_nonzero(original[:, 320:, :3] != filled[:, 320:, :3]) > 100
        viewer.paused = False
        viewer.previous_time -= 1 / 60
        canvas.draw()
        moving = np.frombuffer(
            viewer.renderer.device.queue.read_buffer(viewer.renderer.particles),
            dtype=np.float32,
        ).copy()
        assert not np.array_equal(moving, initialized)
        viewer.paused = True
        canvas.draw()
        np.testing.assert_array_equal(
            np.frombuffer(
                viewer.renderer.device.queue.read_buffer(viewer.renderer.particles),
                dtype=np.float32,
            ),
            moving,
        )
        viewer.elapsed = 0
        viewer.reset = True
        canvas.set_logical_size(1024, 768)
        resized = np.asarray(canvas.draw())
        reset = np.frombuffer(
            viewer.renderer.device.queue.read_buffer(viewer.renderer.particles),
            dtype=np.float32,
        )
        assert resized.shape == (768, 1024, 4)
        np.testing.assert_array_equal(reset, initialized)
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()
