# ruff: noqa: D101, D102

import numpy
import pygfx
from rendercanvas import BaseRenderCanvas


class Viewer:
    def __init__(self, canvas: BaseRenderCanvas, colors: numpy.ndarray) -> None:
        self.canvas = canvas
        self.renderer = pygfx.WgpuRenderer(canvas)
        image = pygfx.Image(
            pygfx.Geometry(grid=colors), pygfx.ImageBasicMaterial(clim=(0, 1))
        )
        image.local.scale_y = -1
        self.scene = pygfx.Scene()
        self.scene.add(image)
        self.camera = pygfx.OrthographicCamera()
        self.camera.show_object(image, match_aspect=True)
        self.controller = pygfx.PanZoomController(
            self.camera, register_events=self.renderer
        )
        canvas.request_draw(self.draw_frame)

    def draw_frame(self) -> None:
        self.renderer.render(self.scene, self.camera)
        self.canvas.request_draw()
