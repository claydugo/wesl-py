import numpy

from examples.heightfield.compute import render

random = numpy.random.default_rng(21)
impulse = numpy.zeros((17, 31), dtype=numpy.float32)
impulse[0, 0] = 1
impulse[8, 15] = 1
cases = [
    numpy.ones((1, 1), dtype=numpy.float32),
    numpy.linspace(-1, 1, 17, dtype=numpy.float32).reshape(1, 17),
    numpy.linspace(-1, 1, 19, dtype=numpy.float32).reshape(19, 1),
    impulse,
    random.random((19, 37), dtype=numpy.float32)[:, ::-1],
]
for heights in cases:
    height, width = heights.shape
    padded = numpy.pad(heights.astype(numpy.float64), 1, mode="edge")
    gradient = numpy.stack(
        (
            (padded[1:-1, 2:] - padded[1:-1, :-2]) * (width - 1) / 4,
            (padded[2:, 1:-1] - padded[:-2, 1:-1]) * (height - 1) / 4,
        ),
        axis=-1,
    )
    normal = numpy.concatenate((-gradient, numpy.ones((height, width, 1))), axis=-1)
    normal /= numpy.linalg.norm(normal, axis=-1, keepdims=True)
    for mode, direction in (
        ("edges", (0.6, -0.5, 0.8)),
        ("normals", (0.6, -0.5, 0.8)),
        ("shaded", (0.6, -0.5, 0.8)),
        ("shaded", (0, 0, 1)),
        ("shaded", (0, 0, -1)),
    ):
        if mode == "edges":
            magnitude = 1 - numpy.exp(-numpy.linalg.norm(gradient, axis=-1))
            reference = numpy.repeat(magnitude[:, :, None], 3, axis=-1)
        elif mode == "normals":
            reference = 0.5 + 0.5 * normal
        else:
            light = numpy.asarray(direction, dtype=numpy.float64)
            light /= numpy.linalg.norm(light)
            dot = numpy.sum(normal * light, axis=-1)
            diffuse = numpy.maximum(dot, 0)
            reflected = 2 * dot[:, :, None] * normal - light
            highlight = numpy.where(
                diffuse > 0, numpy.maximum(reflected[:, :, 2], 0) ** 12, 0
            )
            copper = numpy.array([0.55, 0.22, 0.07]) * (
                0.16 + 0.84 * diffuse[:, :, None]
            )
            reference = (
                copper + numpy.array([1, 0.85, 0.6]) * 0.65 * highlight[:, :, None]
            ) ** (1 / 2.2)
        expected = numpy.round(255 * numpy.clip(reference, 0, 1)).astype(numpy.int16)
        actual = render(heights, mode, direction)
        numpy.testing.assert_allclose(actual[:, :, :3], expected, rtol=0, atol=1)
        numpy.testing.assert_array_equal(actual[:, :, 3], 255)
    print(f"Verified heightfield: shape={heights.shape}")
