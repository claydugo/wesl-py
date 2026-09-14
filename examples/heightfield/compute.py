from pathlib import Path

import numpy
import wesl
from wgpu.utils.compute import compute_with_buffers


def render(
    heights: numpy.ndarray,
    mode: str,
    light: tuple[float, float, float] = (0.6, -0.5, 0.8),
) -> numpy.ndarray:
    height, width = heights.shape
    shader = wesl.compile_file(
        Path(__file__).with_name("render.wesl"),
        root_directory=Path(__file__).parent.parent,
        options=wesl.CompileOptions(features=wesl.Features(flags={mode: True})),
    )
    constants = {"width": width, "height": height}
    if mode == "shaded":
        constants.update(light_x=light[0], light_y=light[1], light_z=light[2])
    output = compute_with_buffers(
        {0: numpy.ascontiguousarray(heights, dtype=numpy.float32)},
        {1: (height * width, "I")},
        shader.wgsl,
        constants=constants,
        n=((width + 15) // 16, (height + 15) // 16, 1),
    )
    return numpy.frombuffer(output[1], dtype=numpy.uint8).reshape(height, width, 4)
