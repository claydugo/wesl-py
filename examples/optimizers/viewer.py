from enum import StrEnum
from pathlib import Path
from time import perf_counter

import numpy as np
import wesl
import wgpu
from imgui_bundle import imgui
from numpy.typing import NDArray
from rendercanvas import BaseRenderCanvas
from wgpu.utils.imgui import ImguiRenderer

from examples.optimizers.renderer import Renderer
from examples.style import apply_style


class Dataset(StrEnum):
    SPIRAL = "Spiral"
    MOONS = "Moons"
    CIRCLES = "Circles"
    XOR = "XOR"


def create_samples(
    random: np.random.Generator, dataset: Dataset
) -> NDArray[np.float32]:
    label = np.repeat([0.0, 1.0], 200)
    if dataset == Dataset.SPIRAL:
        radius = np.sqrt(random.uniform(0.05, 1.0, 400))
        angle = radius * 3.5 * np.pi + label * np.pi
        positions = radius[:, None] * np.stack([np.cos(angle), np.sin(angle)], 1)
    elif dataset == Dataset.MOONS:
        angle = random.uniform(0, np.pi, 400)
        positions = np.where(
            label[:, None] == 1,
            np.stack([1 - np.cos(angle), 0.5 - np.sin(angle)], 1),
            np.stack([np.cos(angle), np.sin(angle)], 1),
        )
        positions = (positions - [0.5, 0.25]) * 0.7
    elif dataset == Dataset.CIRCLES:
        radius = np.where(label == 1, 0.85, 0.4)
        angle = random.uniform(0, 2 * np.pi, 400)
        positions = radius[:, None] * np.stack([np.cos(angle), np.sin(angle)], 1)
    else:
        positions = random.uniform(0.1, 1, (400, 2)) * random.choice([-1, 1], (400, 2))
        label = (positions[:, 0] * positions[:, 1] > 0).astype(np.float64)
    samples = np.zeros((400, 4), dtype=np.float32)
    samples[:, :2] = positions + random.normal(0, 0.04, (400, 2))
    samples[:, 2] = label
    return samples


class Viewer:
    def __init__(self, canvas: BaseRenderCanvas) -> None:
        self.canvas = canvas
        self.renderer = Renderer(canvas, 16)
        self.random = np.random.default_rng(3)
        self.dataset = Dataset.SPIRAL
        self.samples = create_samples(self.random, self.dataset)
        self.steps_per_frame = 2
        self.paused = False
        self.error = None
        self.panels = []
        self.checked_time = perf_counter()
        self.reset()
        self.gui = ImguiRenderer(
            self.renderer.device, canvas, render_target_format=self.renderer.format
        )
        apply_style()
        self.gui.set_gui(self.draw_controls)
        canvas.request_draw(self.draw_frame)

    def reset(self) -> None:
        layout = self.renderer.layout
        width = layout["width"]
        parameters = np.zeros(layout["parameter_count"], dtype=np.float32)
        parameters[layout["first_weights"] : layout["first_biases"]] = (
            self.random.normal(0, 2.0, 2 * width)
        )
        parameters[layout["second_weights"] : layout["second_biases"]] = (
            self.random.normal(0, width**-0.5, width * width)
        )
        parameters[layout["output_weights"] : layout["output_bias"]] = (
            self.random.normal(0, width**-0.5, width)
        )
        self.renderer.reset(self.samples, parameters)
        self.histories = [np.zeros((0, 4), dtype=np.float32) for _ in range(3)]
        self.perfect_steps = [None, None, None]

    def rebuild(self) -> None:
        try:
            self.renderer.build()
        except wesl.CompileError as error:
            lines = []
            for diagnostic in error.diagnostics:
                location = Path(diagnostic.filename or diagnostic.module or "").name
                if diagnostic.line is not None:
                    location += f":{diagnostic.line}:{diagnostic.column}"
                lines.append(f"{location}: {diagnostic.message}")
                if diagnostic.filename is not None:
                    path = Path(diagnostic.filename)
                    if path.exists():
                        self.renderer.modified.setdefault(path, path.stat().st_mtime_ns)
            self.error = "\n".join(lines) or str(error)
            return
        except (wgpu.GPUError, OSError) as error:
            self.error = str(error)
            return
        self.error = None
        self.reset()

    def train(self, step_count: int, *, read: bool) -> None:
        self.renderer.train(step_count)
        if read or self.renderer.frame % 15 == 1:
            self.histories = self.renderer.read_histories()
            for index, history in enumerate(self.histories):
                perfect = history[history[:, 1] == 1]
                if self.perfect_steps[index] is None and len(perfect):
                    self.perfect_steps[index] = int(perfect[0, 2])

    def draw_decay(self, label: str, rule_index: int, override: str) -> None:
        constants = self.renderer.rules[rule_index].constants
        _, constants[override] = imgui.slider_float(
            label, constants[override], 0.5, 0.9999, "%.4f"
        )
        if imgui.is_item_deactivated_after_edit():
            try:
                self.renderer.apply_constants()
            except wgpu.GPUError as error:
                self.error = str(error)

    def draw_controls(self) -> None:
        imgui.set_next_window_pos((16, 16), imgui.Cond_.always)
        imgui.set_next_window_size((280, 0), imgui.Cond_.always)
        imgui.begin(
            "Optimizer comparison",
            flags=imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_collapse,
        )
        imgui.text_wrapped(
            "Three copies of one network learn the same dataset. "
            "Each copy uses a different optimizer."
        )
        imgui.spacing()
        imgui.push_item_width(120)
        datasets = list(Dataset)
        changed, selected = imgui.combo(
            "Dataset", datasets.index(self.dataset), [item.value for item in datasets]
        )
        if changed:
            self.dataset = datasets[selected]
            self.samples = create_samples(self.random, self.dataset)
            self.reset()
        _, self.steps_per_frame = imgui.slider_int(
            "Steps per frame", self.steps_per_frame, 1, 20
        )
        imgui.separator()
        imgui.text("Learning rates")
        for rule, (minimum, maximum) in zip(
            self.renderer.rules,
            ((0.01, 5.0), (0.001, 0.5), (0.0005, 0.1)),
            strict=True,
        ):
            _, rule.learning_rate = imgui.slider_float(
                rule.title,
                rule.learning_rate,
                minimum,
                maximum,
                "%.4f",
                imgui.SliderFlags_.logarithmic,
            )
        imgui.text("Decay rates")
        imgui.push_id("decay")
        self.draw_decay("Momentum", 1, "0")
        self.draw_decay("Adam mean", 2, "0")
        self.draw_decay("Adam variance", 2, "1")
        imgui.pop_id()
        imgui.separator()
        _, self.paused = imgui.checkbox("Pause", self.paused)
        if self.paused:
            imgui.same_line()
            if imgui.button("Step"):
                self.train(1, read=True)
        if imgui.button("Reset weights"):
            self.reset()
        imgui.pop_item_width()
        imgui.separator()
        imgui.text_wrapped(
            f"Saving any of {len(self.renderer.modified)} shader files rebuilds "
            "the pipelines and resets the weights."
        )
        if self.error is not None:
            imgui.push_style_color(imgui.Col_.text, (1.0, 0.45, 0.4, 1.0))
            imgui.text_wrapped(self.error)
            imgui.pop_style_color()
        imgui.separator()
        imgui.text_wrapped(
            "The background shows the predicted class. The white line is the "
            "decision boundary. White rings mark misclassified points."
        )
        imgui.end()
        self.draw_panels()

    def draw_panels(self) -> None:
        if not self.panels:
            return
        for index, (rule, history, (left, top, size)) in enumerate(
            zip(self.renderer.rules, self.histories, self.panels, strict=True)
        ):
            imgui.set_next_window_pos((left, top - 144), imgui.Cond_.always)
            imgui.set_next_window_size((size, 136), imgui.Cond_.always)
            imgui.begin(
                rule.title,
                flags=imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_inputs,
            )
            imgui.text(rule.title)
            if len(history):
                loss, accuracy, step = history[-1, :3]
                imgui.text(f"Step {step:.0f}: loss {loss:.4f}, accuracy {accuracy:.0%}")
                imgui.plot_lines(
                    "##loss",
                    np.log10(np.maximum(history[:, 0], 1e-4)).astype(np.float32),
                    scale_min=-4.0,
                    scale_max=0.0,
                    graph_size=(size - 16, 48),
                )
            if self.perfect_steps[index] is not None:
                imgui.text(f"Every point correct at step {self.perfect_steps[index]}")
            imgui.end()

    def draw_frame(self) -> None:
        current_time = perf_counter()
        if current_time > self.checked_time + 0.25:
            self.checked_time = current_time
            if self.renderer.changed():
                self.rebuild()
        if not self.paused:
            self.train(self.steps_per_frame, read=False)
        canvas_width, canvas_height = self.canvas.get_logical_size()
        if canvas_width == 0 or canvas_height == 0:
            self.canvas.request_draw()
            return
        size = min((canvas_width - 328) / 3 - 8, canvas_height - 168)
        self.panels = []
        if size > 0:
            self.panels = [(312 + index * (size + 8), 152, size) for index in range(3)]
        ratio = self.canvas.get_pixel_ratio()
        self.renderer.draw(
            [
                (left * ratio, top * ratio, size * ratio, size * ratio)
                for left, top, size in self.panels
            ]
        )
        self.gui.render()
        self.canvas.request_draw()
