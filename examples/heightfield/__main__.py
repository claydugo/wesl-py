import argparse
import subprocess
from pathlib import Path

import imageio.v3 as imageio
import numpy

from examples.heightfield.compute import render

parser = argparse.ArgumentParser(description="Turn a height field into a lit surface.")
parser.add_argument(
    "--output", type=Path, required=True, help="Directory for exported images."
)
parser.add_argument(
    "--show", action="store_true", help="Open the relighting animation."
)
arguments = parser.parse_args()
arguments.output.mkdir(parents=True, exist_ok=True)
print("Rendering heightfield images and animation...", flush=True)  # noqa: T201

y, x = numpy.mgrid[-1:1:512j, -1:1:512j]
radius = numpy.hypot(x + 0.3, y + 0.1)
heights = (
    0.45 * numpy.exp(-4 * ((x + 0.25) ** 2 + (y + 0.15) ** 2))
    + 0.3 * numpy.exp(-12 * ((x - 0.5) ** 2 + (y - 0.35) ** 2))
    + 0.06 * numpy.sin(38 * radius) * numpy.exp(-2 * radius**2)
    + 0.06 * numpy.sin(18 * x + 3 * numpy.sin(7 * y)) * numpy.exp(-2 * (x**2 + y**2))
).astype(numpy.float32)
imageio.imwrite(
    arguments.output / "height.png",
    numpy.round(255 * (heights - heights.min()) / numpy.ptp(heights)).astype(
        numpy.uint8
    ),
)
for mode in ("edges", "normals", "shaded"):
    imageio.imwrite(arguments.output / f"{mode}.png", render(heights, mode))

frames = [
    render(heights, "shaded", (numpy.cos(angle), numpy.sin(angle), 0.8))
    for angle in numpy.linspace(0, 2 * numpy.pi, 36, endpoint=False)
]
imageio.imwrite(arguments.output / "relight.gif", frames, duration=80, loop=0)
print(f"Saved images to {arguments.output.resolve()}", flush=True)  # noqa: T201
if arguments.show:
    subprocess.run(  # noqa: S603
        ["xdg-open", str((arguments.output / "relight.gif").resolve())],  # noqa: S607
        check=True,
    )
