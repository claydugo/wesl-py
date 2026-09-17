import numpy as np
import pytest
import wesl
from wesl.testing import Buffer, ShaderRunner, Texture


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("horizontal_scale", "vertical_scale"),
    [(1, 1), (2, 1), (1, 2)],
    ids=["square", "wide", "tall"],
)
def test_tinted_image(
    wesl_compiler: wesl.Compiler,
    wesl_runner: ShaderRunner,
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
    output = wesl_runner.fragment(
        shader,
        size=(2 * horizontal_scale, 2 * vertical_scale),
        resources={
            (0, 0): Texture(data=pixels, format="rgba8unorm"),
            (0, 1): wesl_runner.device.create_sampler(
                mag_filter="nearest", min_filter="nearest"
            ),
            (0, 2): Buffer(data=multiplier, uniform=True),
        },
    )
    expected = pixels.astype(np.float32) / 255 * multiplier
    np.testing.assert_allclose(output, expected, rtol=1e-6, atol=1e-7)
