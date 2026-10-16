from enum import StrEnum
from time import perf_counter

import numpy as np
from imgui_bundle import imgui
from rendercanvas import BaseRenderCanvas
from wgpu.utils.imgui import ImguiRenderer

from examples.sorting.renderer import Renderer
from examples.style import apply_style


class Input(StrEnum):
    RANDOM = "Random"
    REVERSED = "Reversed"
    NEARLY_SORTED = "Nearly sorted"
    FEW_UNIQUE = "Few unique"


class Viewer:
    def __init__(self, canvas: BaseRenderCanvas) -> None:
        self.canvas = canvas
        self.renderer = Renderer(canvas)
        self.random = np.random.default_rng(7)
        self.counts = [128, 256, 512, 1024, 2048]
        self.count = 256
        self.input = Input.RANDOM
        self.rate = 40.0
        self.budget = 0.0
        self.paused = False
        self.dots = False
        self.panels = []
        self.previous_time = perf_counter()
        self.shuffle()
        self.gui = ImguiRenderer(
            self.renderer.device, canvas, render_target_format=self.renderer.format
        )
        apply_style()
        self.gui.set_gui(self.draw_controls)
        canvas.request_draw(self.draw_frame)

    def shuffle(self) -> None:
        if self.input == Input.FEW_UNIQUE:
            values = self.random.integers(0xFF000000, 2**32, 8, dtype=np.uint32)[
                self.random.integers(0, 8, self.count)
            ]
        else:
            values = self.random.integers(
                0xFF000000, 2**32, self.count, dtype=np.uint32
            )
        if self.input == Input.REVERSED:
            values = self.renderer.presort(values)[::-1].copy()
        elif self.input == Input.NEARLY_SORTED:
            values = self.renderer.presort(values)
            for index in self.random.choice(self.count - 8, self.count // 20):
                partner = index + self.random.integers(1, 8)
                values[[index, partner]] = values[[partner, index]]
        self.values = values
        self.renderer.upload(values)

    def draw_controls(self) -> None:
        imgui.set_next_window_pos((16, 16), imgui.Cond_.always)
        imgui.set_next_window_size((280, 0), imgui.Cond_.always)
        imgui.begin(
            "Parallel sorting",
            flags=imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_collapse,
        )
        imgui.text_wrapped("Three GPU sorts order the same random colors.")
        imgui.spacing()
        imgui.push_item_width(150)
        keys = self.renderer.keys
        changed, selected = imgui.combo(
            "Key",
            keys.index(self.renderer.key),
            [key.stem.capitalize() for key in keys],
        )
        if changed:
            self.renderer.select_key(keys[selected])
            if self.input in (Input.REVERSED, Input.NEARLY_SORTED):
                self.shuffle()
            else:
                self.renderer.upload(self.values)
        inputs = list(Input)
        changed, selected = imgui.combo(
            "Input", inputs.index(self.input), [item.value for item in inputs]
        )
        if changed:
            self.input = inputs[selected]
            self.shuffle()
        changed, selected = imgui.combo(
            "Values",
            self.counts.index(self.count),
            [str(count) for count in self.counts],
        )
        if changed:
            self.count = self.counts[selected]
            self.shuffle()
        _, self.rate = imgui.slider_float(
            "Speed",
            self.rate,
            1.0,
            600.0,
            "%.0f stages/s",
            imgui.SliderFlags_.logarithmic,
        )
        _, self.dots = imgui.checkbox("Dots", self.dots)
        _, self.paused = imgui.checkbox("Pause", self.paused)
        if self.paused:
            imgui.same_line()
            if imgui.button("Step"):
                self.renderer.step()
        if imgui.button("New input"):
            self.shuffle()
        imgui.pop_item_width()
        imgui.separator()
        imgui.text_wrapped(
            "Bar height shows the key. Dim bars are out of order with a "
            "neighbor. White caps mark values that moved in the latest stage."
        )
        imgui.end()
        self.draw_panels()

    def draw_panels(self) -> None:
        if not self.panels:
            return
        for sort, (left, top, width, _) in zip(
            self.renderer.sorts, self.panels, strict=True
        ):
            imgui.set_next_window_pos((left, top - 72), imgui.Cond_.always)
            imgui.set_next_window_size((width, 64), imgui.Cond_.always)
            imgui.begin(
                sort.title,
                flags=imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_inputs,
            )
            imgui.text(sort.title)
            if sort.finished:
                imgui.text(f"Sorted in {len(sort.schedule)} stages")
            else:
                imgui.text(f"Stage {sort.stage} of {len(sort.schedule)}")
            imgui.end()

    def draw_frame(self) -> None:
        current_time = perf_counter()
        delta = min(current_time - self.previous_time, 1 / 30)
        self.previous_time = current_time
        if not self.paused:
            self.budget += delta * self.rate
            step_count = int(self.budget)
            self.budget -= step_count
            for _ in range(min(step_count, 32)):
                self.renderer.step()
        canvas_width, canvas_height = self.canvas.get_logical_size()
        if canvas_width == 0 or canvas_height == 0:
            self.canvas.request_draw()
            return
        panel_width = (canvas_width - 328) / 3 - 8
        panel_height = canvas_height - 104
        self.panels = []
        if panel_width > 0 and panel_height > 0:
            self.panels = [
                (312 + index * (panel_width + 8), 88, panel_width, panel_height)
                for index in range(3)
            ]
        ratio = self.canvas.get_pixel_ratio()
        self.renderer.draw(
            [
                (left * ratio, top * ratio, width * ratio, height * ratio)
                for left, top, width, height in self.panels
            ],
            dots=self.dots,
        )
        self.gui.render()
        self.canvas.request_draw()
