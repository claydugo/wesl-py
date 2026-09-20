import numpy as np
import pytest
import wesl
import wgpu
from wesl.testing import Buffer, ShaderRunner


@pytest.mark.gpu
def test_compute_to_fragment(
    wesl_compiler: wesl.Compiler, wesl_runner: ShaderRunner
) -> None:
    compute_shader = wesl_compiler.compile_file("gradient_compute.wesl")
    fragment_shader = wesl_compiler.compile_file("tint.wesl")
    texture = wesl_runner.device.create_texture(
        size=(8, 2, 1),
        format="rgba16float",
        usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.TEXTURE_BINDING,
    )
    multiplier = np.array([0.5, 0.75, 0.25, 1], dtype=np.float32)
    try:
        wesl_runner.compute(
            compute_shader, resources={(0, 0): texture}, workgroups=(2, 1, 1)
        )
        output = wesl_runner.fragment(
            fragment_shader,
            size=(8, 2),
            resources={
                (0, 0): texture,
                (0, 1): wesl_runner.device.create_sampler(
                    mag_filter="nearest", min_filter="nearest"
                ),
                (0, 2): Buffer(data=multiplier, uniform=True),
            },
        )
    finally:
        texture.destroy()
    expected = np.empty((2, 8, 4), dtype=np.float32)
    expected[:, :, 0] = np.arange(8, dtype=np.float32) / 8 * 2
    if wesl_compiler.options.features.flags["clamped"]:
        expected[:, :, 0] = np.clip(expected[:, :, 0], 0, 1)
    expected[:, :, 0] *= 0.5
    expected[:, :, 1] = np.arange(2, dtype=np.float32)[:, None] / 2
    expected[:, :, 2] = 0.25
    expected[:, :, 3] = 1
    np.testing.assert_allclose(output, expected * multiplier, rtol=1e-6, atol=1e-7)
