import argparse
import webbrowser
from pathlib import Path

import imageio.v3 as imageio
import numpy
import wesl
from wgpu.utils.compute import compute_with_buffers

parser = argparse.ArgumentParser(description="Render Mandelbrot and Julia fractals.")
parser.add_argument(
    "--output", type=Path, required=True, help="Directory for exported images."
)
parser.add_argument("--show", action="store_true", help="Open the rendered images.")
arguments = parser.parse_args()
arguments.output.mkdir(parents=True, exist_ok=True)
width, height = 640, 480

for name, julia in (("mandelbrot", False), ("julia", True)):
    result = wesl.compile_file(
        Path(__file__).with_name("render.wesl"),
        root_directory=Path(__file__).parent.parent,
        features={"julia": julia},
    )
    output = compute_with_buffers(
        {},
        {0: (width * height, "I")},
        result.wgsl,
        constants={"width": width, "height": height},
        n=((width + 15) // 16, (height + 15) // 16, 1),
    )
    image = numpy.frombuffer(output[0], dtype=numpy.uint8).reshape(height, width, 4)
    filename = arguments.output / f"{name}.png"
    imageio.imwrite(filename, image)
    if arguments.show:
        webbrowser.open(filename.resolve().as_uri())
