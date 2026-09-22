from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pytest_regressions.ndarrays_regression import NDArraysRegressionFixture

numpy = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")
pytest.importorskip("pytest_regressions")


@pytest.mark.gpu
def test_gradient(
    wesl_compiler: wesl.Compiler,
    wesl_device: wgpu.GPUDevice,
    ndarrays_regression: "NDArraysRegressionFixture",
) -> None:
    shader = wesl_compiler.compile_file("gradient.wesl")
    pipeline = wesl_device.create_render_pipeline(
        layout="auto",
        vertex={
            "module": wesl_device.create_shader_module(
                code=wesl_compiler.compile_file("fullscreen.wesl").wgsl,
            ),
            "entry_point": "main",
        },
        fragment={
            "module": wesl_device.create_shader_module(code=shader.wgsl),
            "entry_point": "main",
            "targets": [{"format": "rgba32float"}],
        },
    )
    target = wesl_device.create_texture(
        size=(8, 4, 1),
        format="rgba32float",
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
    )
    try:
        encoder = wesl_device.create_command_encoder()
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": target.create_view(),
                    "load_op": "clear",
                    "store_op": "store",
                    "clear_value": (0.0, 0.0, 0.0, 0.0),
                }
            ]
        )
        render_pass.set_pipeline(pipeline)
        render_pass.draw(3)
        render_pass.end()
        wesl_device.queue.submit([encoder.finish()])
        pixels = numpy.frombuffer(
            wesl_device.queue.read_texture(
                {"texture": target},
                {"bytes_per_row": 128},
                target.size,
            ),
            dtype=numpy.float32,
        ).reshape(4, 8, 4)
        ndarrays_regression.check(
            {"pixels": pixels},
            default_tolerance={"rtol": 1e-6, "atol": 1e-7},
        )
    finally:
        target.destroy()
