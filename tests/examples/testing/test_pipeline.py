from contextlib import ExitStack

import pytest
import wesl

np = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")


@pytest.mark.gpu
def test_compute_to_fragment(
    wesl_compiler: wesl.Compiler, wesl_device: wgpu.GPUDevice
) -> None:
    compute_shader = wesl_compiler.compile_file(
        "tests/examples/testing/shaders/gradient_compute.wesl"
    )
    fragment_shader = wesl_compiler.compile_file(
        "tests/examples/testing/shaders/tint.wesl"
    )
    multiplier = np.array([0.5, 0.75, 0.25, 1], dtype=np.float32)
    with ExitStack() as stack:
        texture = wesl_device.create_texture(
            size=(8, 2, 1),
            format="rgba16float",
            usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.TEXTURE_BINDING,
        )
        stack.callback(texture.destroy)
        uniform = wesl_device.create_buffer_with_data(
            data=multiplier,
            usage=wgpu.BufferUsage.UNIFORM,
        )
        stack.callback(uniform.destroy)
        target = wesl_device.create_texture(
            size=(8, 2, 1),
            format="rgba32float",
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        stack.callback(target.destroy)
        compute_pipeline = wesl_device.create_compute_pipeline(
            layout="auto",
            compute={
                "module": wesl_device.create_shader_module(code=compute_shader.wgsl),
                "entry_point": "main",
            },
        )
        compute_group = wesl_device.create_bind_group(
            layout=compute_pipeline.get_bind_group_layout(0),
            entries=[{"binding": 0, "resource": texture.create_view()}],
        )
        render_pipeline = wesl_device.create_render_pipeline(
            layout="auto",
            vertex={
                "module": wesl_device.create_shader_module(
                    code=wesl_compiler.compile_file(
                        "tests/examples/testing/shaders/fullscreen.wesl"
                    ).wgsl,
                ),
                "entry_point": "main",
            },
            fragment={
                "module": wesl_device.create_shader_module(code=fragment_shader.wgsl),
                "entry_point": "main",
                "targets": [{"format": "rgba32float"}],
            },
        )
        render_group = wesl_device.create_bind_group(
            layout=render_pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": 0, "resource": texture.create_view()},
                {
                    "binding": 1,
                    "resource": wesl_device.create_sampler(
                        mag_filter="nearest",
                        min_filter="nearest",
                    ),
                },
                {"binding": 2, "resource": {"buffer": uniform}},
            ],
        )
        encoder = wesl_device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(compute_pipeline)
        compute_pass.set_bind_group(0, compute_group)
        compute_pass.dispatch_workgroups(2, 1, 1)
        compute_pass.end()
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
        render_pass.set_pipeline(render_pipeline)
        render_pass.set_bind_group(0, render_group)
        render_pass.draw(3)
        render_pass.end()
        wesl_device.queue.submit([encoder.finish()])
        output = np.frombuffer(
            wesl_device.queue.read_texture(
                {"texture": target},
                {"bytes_per_row": 128},
                target.size,
            ),
            dtype=np.float32,
        ).reshape(2, 8, 4)
    expected = np.empty((2, 8, 4), dtype=np.float32)
    expected[:, :, 0] = np.arange(8, dtype=np.float32) / 8 * 2
    if wesl_compiler.options.features.flags["clamped"]:
        expected[:, :, 0] = np.clip(expected[:, :, 0], 0, 1)
    expected[:, :, 0] *= 0.5
    expected[:, :, 1] = np.arange(2, dtype=np.float32)[:, None] / 2
    expected[:, :, 2] = 0.25
    expected[:, :, 3] = 1
    np.testing.assert_allclose(output, expected * multiplier, rtol=1e-6, atol=1e-7)
