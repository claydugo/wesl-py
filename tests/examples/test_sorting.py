import logging
from importlib import import_module
from pathlib import Path

import pytest
import wesl

np = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")
pytest.importorskip("imgui_bundle")


@pytest.mark.gpu
@pytest.mark.parametrize(
    "key",
    sorted((Path(__file__).parents[2] / "examples/sorting/keys").glob("*.wesl")),
    ids=lambda key: key.stem,
)
def test_sorting_viewer(caplog: pytest.LogCaptureFixture, key: Path) -> None:
    canvas = import_module("rendercanvas.offscreen").RenderCanvas(size=(1440, 900))
    viewer_module = import_module("examples.sorting.viewer")
    viewer = viewer_module.Viewer(canvas)
    renderer = viewer.renderer
    compiler = wesl.Compiler.from_project(
        Path(__file__).parent,
        modules={"package::examples::sorting::key": key.read_text()},
    )
    pipeline = renderer.device.create_compute_pipeline(
        layout="auto",
        compute={
            "module": renderer.device.create_shader_module(
                code=compiler.compile_source(
                    "import package::examples::sorting::key::key;\n"
                    "@group(0) @binding(0) var<storage, read_write> values: "
                    "array<u32>;\n"
                    "@compute @workgroup_size(64)\n"
                    "fn main(@builtin(global_invocation_id) index: vec3u) {\n"
                    "    values[index.x] = key(values[index.x]);\n"
                    "}\n"
                ).wgsl
            ),
            "entry_point": "main",
        },
    )

    def compute_keys(values: np.ndarray) -> np.ndarray:
        buffer = renderer.device.create_buffer_with_data(
            data=values, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
        )
        encoder = renderer.device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        compute_pass.set_bind_group(
            0,
            renderer.device.create_bind_group(
                layout=pipeline.get_bind_group_layout(0),
                entries=[{"binding": 0, "resource": {"buffer": buffer}}],
            ),
        )
        compute_pass.dispatch_workgroups(len(values) // 64)
        compute_pass.end()
        renderer.device.queue.submit([encoder.finish()])
        return np.frombuffer(renderer.device.queue.read_buffer(buffer), np.uint32)

    try:
        renderer.select_key(key)
        viewer.paused = True
        viewer.count = 2048
        viewer.input = viewer_module.Input.REVERSED
        viewer.shuffle()
        assert np.all(
            np.diff(compute_keys(renderer.read(renderer.sorts[0])).astype(np.int64))
            <= 0
        )
        viewer.input = viewer_module.Input.RANDOM
        viewer.shuffle()
        values = renderer.read(renderer.sorts[0])
        shuffled = np.asarray(canvas.draw()).copy()
        for _ in range(2048):
            renderer.step()
        keys = compute_keys(values)
        order = np.argsort(keys, kind="stable")
        np.testing.assert_array_equal(renderer.read(renderer.sorts[2]), values[order])
        for sort in renderer.sorts[:2]:
            result = renderer.read(sort)
            np.testing.assert_array_equal(np.sort(result), np.sort(values))
            np.testing.assert_array_equal(compute_keys(result), keys[order])
        assert [sort.stage for sort in renderer.sorts] == [66, 2048, 10]
        sorted_frame = np.asarray(canvas.draw()).copy()
        assert sorted_frame[100:, 320:, :3].mean() > shuffled[100:, 320:, :3].mean()
        viewer.dots = True
        canvas.draw()
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()
