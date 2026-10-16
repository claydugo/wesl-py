from rendercanvas.glfw import RenderCanvas, loop

from examples.sorting.viewer import Viewer

canvas = RenderCanvas(title="WESL | Parallel sorting")
canvas.set_logical_size(1440, 900)
viewer = Viewer(canvas)
loop.run()
