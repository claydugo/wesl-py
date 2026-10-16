from rendercanvas.glfw import RenderCanvas, loop

from examples.optimizers.viewer import Viewer

canvas = RenderCanvas(title="WESL | Optimizer comparison")
canvas.set_logical_size(1440, 720)
viewer = Viewer(canvas)
loop.run()
