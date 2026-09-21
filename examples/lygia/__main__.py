import argparse
from pathlib import Path

import imageio.v3 as imageio
import numpy
import wgpu

from .compute import colorize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("lygia.png"))
    parser.add_argument("--minimum", type=float, default=0.0)
    parser.add_argument("--maximum", type=float, default=1.0)
    arguments = parser.parse_args()
    if arguments.input is None:
        vertical, horizontal = numpy.mgrid[-1:1:257j, -1:1:385j]
        values = numpy.exp(-12 * ((horizontal + 0.3) ** 2 + vertical**2))
        values += 0.6 * numpy.exp(
            -40 * ((horizontal - 0.4) ** 2 + (vertical - 0.3) ** 2)
        )
        values = values.astype(numpy.float32)
    else:
        values = numpy.asarray(imageio.imread(arguments.input), dtype=numpy.float32)
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    try:
        colors = colorize(
            device,
            values,
            library_directory=arguments.library,
            minimum=arguments.minimum,
            maximum=arguments.maximum,
        )
        imageio.imwrite(arguments.output, numpy.rint(colors * 255).astype(numpy.uint8))
    finally:
        device.destroy()


if __name__ == "__main__":
    main()
