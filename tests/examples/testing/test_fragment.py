from contextlib import ExitStack

import numpy as np
import pytest
import wesl
import wgpu


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("horizontal_scale", "vertical_scale"),
    [(1, 1), (2, 1), (1, 2)],
    ids=["square", "wide", "tall"],
)
def test_tinted_image(
    wesl_compiler: wesl.Compiler,
    wesl_device: wgpu.GPUDevice,
    horizontal_scale: int,
    vertical_scale: int,
) -> None:
    shader = wesl_compiler.compile_file("tint.wesl")
    pixels = np.array(
        [
            [[255, 0, 0, 255], [0, 255, 0, 255]],
            [[0, 0, 255, 255], [128, 64, 32, 255]],
        ],
        dtype=np.uint8,
    )
    pixels = pixels.repeat(vertical_scale, axis=0).repeat(horizontal_scale, axis=1)
    multiplier = np.array([0.5, 0.75, 0.25, 1], dtype=np.float32)
    with ExitStack() as stack:
        texture = wesl_device.create_texture(
            size=(2 * horizontal_scale, 2 * vertical_scale, 1),
            format="rgba8unorm",
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        stack.callback(texture.destroy)
        wesl_device.queue.write_texture(
            {"texture": texture},
            pixels,
            {"bytes_per_row": 2 * horizontal_scale * 4},
            texture.size,
        )
        uniform = wesl_device.create_buffer_with_data(
            data=multiplier,
            usage=wgpu.BufferUsage.UNIFORM,
        )
        stack.callback(uniform.destroy)
        target = wesl_device.create_texture(
            size=(2 * horizontal_scale, 2 * vertical_scale, 1),
            format="rgba32float",
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        stack.callback(target.destroy)
        pipeline = wesl_device.create_render_pipeline(
            layout="auto",
            vertex={
                "module": wesl_device.create_shader_module(
                    code=wesl_compiler.compile_file("fullscreen.wgsl").wgsl,
                ),
                "entry_point": "main",
            },
            fragment={
                "module": wesl_device.create_shader_module(code=shader.wgsl),
                "entry_point": "main",
                "targets": [{"format": "rgba32float"}],
            },
        )
        bind_group = wesl_device.create_bind_group(
            layout=pipeline.get_bind_group_layout(0),
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
        render_pass.set_bind_group(0, bind_group)
        render_pass.draw(3)
        render_pass.end()
        wesl_device.queue.submit([encoder.finish()])
        output = np.frombuffer(
            wesl_device.queue.read_texture(
                {"texture": target},
                {"bytes_per_row": 2 * horizontal_scale * 16},
                target.size,
            ),
            dtype=np.float32,
        ).reshape(2 * vertical_scale, 2 * horizontal_scale, 4)
        expected = pixels.astype(np.float32) / 255 * multiplier
        np.testing.assert_allclose(output, expected, rtol=1e-6, atol=1e-7)
