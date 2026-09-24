import argparse
from pathlib import Path

import imageio.v3 as imageio
import numpy
from rendercanvas.offscreen import RenderCanvas as OffscreenRenderCanvas

from examples.multiscale.common import load_colony
from examples.multiscale.viewer import Viewer

parser = argparse.ArgumentParser(
    description="Explore fluorescence at different scales."
)
parser.add_argument(
    "--screenshot", type=Path, help="Save a PNG without opening a window."
)
arguments = parser.parse_args()
if arguments.screenshot:
    canvas = OffscreenRenderCanvas(size=(1600, 960))
else:
    from rendercanvas.glfw import RenderCanvas, loop

    canvas = RenderCanvas(title="WESL | Multiscale fluorescence")
    canvas.set_logical_size(1600, 960)
channels, colors, labels = load_colony()
viewer = Viewer(canvas, channels, colors, labels)
viewer.settings.update(
    center_x=916.0,
    center_y=976.0,
    maximum_radius=880.0,
)
if isinstance(canvas, OffscreenRenderCanvas):
    for _ in range(3):
        frame = canvas.draw()
    imageio.imwrite(arguments.screenshot, numpy.asarray(frame))
else:
    loop.run()
