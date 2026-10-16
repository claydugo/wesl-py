from rendercanvas.glfw import RenderCanvas, loop

from examples.sdf.viewer import Viewer

canvas = RenderCanvas(title="WESL | SDF playground")
canvas.set_logical_size(1440, 900)
viewer = Viewer(canvas)
loop.run()
