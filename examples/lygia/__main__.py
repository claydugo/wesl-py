import argparse
from pathlib import Path

import imageio.v3 as imageio
import numpy
import wgpu
from rendercanvas.glfw import RenderCanvas, loop
from rendercanvas.offscreen import RenderCanvas as OffscreenRenderCanvas

from .viewer import Viewer


def main() -> None:
    parser = argparse.ArgumentParser(description="Explore a procedural landscape.")
    parser.add_argument("--library", type=Path, default=Path(".wesl/lygia"))
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--screenshot", type=Path)
    arguments = parser.parse_args()
    if not -2147483648 <= arguments.seed <= 2147483647:  # noqa: PLR2004
        parser.error("--seed must be between -2147483648 and 2147483647")
    if arguments.screenshot:
        canvas = OffscreenRenderCanvas(size=(1440, 900))
    else:
        canvas = RenderCanvas(title="WESL | Archipelago")
        canvas.set_logical_size(1440, 900)
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    try:
        Viewer(canvas, device, library_directory=arguments.library, seed=arguments.seed)
        if isinstance(canvas, OffscreenRenderCanvas):
            for _ in range(3):
                frame = canvas.draw()
            imageio.imwrite(arguments.screenshot, numpy.asarray(frame))
        else:
            loop.run()
    finally:
        canvas.close()
        device.destroy()


if __name__ == "__main__":
    main()
