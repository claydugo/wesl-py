from collections.abc import Mapping
from dataclasses import dataclass
from os import PathLike, fspath
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import wgpu

from . import CompileOptions, CompileResult, Diagnostic, _native

__all__ = [
    "Binding",
    "Buffer",
    "Resource",
    "ShaderAssertionError",
    "ShaderRunner",
    "ShaderTestDisabledError",
    "ShaderTestResult",
    "Texture",
]


@dataclass(kw_only=True)
class Buffer:
    data: npt.NDArray[Any]
    uniform: bool = False


@dataclass(kw_only=True)
class Texture:
    data: npt.NDArray[Any]
    format: str
    dimension: str = "2d"
    view_dimension: str | None = None
    storage: bool = False


type Binding = tuple[int, int]
type Resource = (
    Buffer
    | Texture
    | wgpu.GPUBuffer
    | wgpu.GPUTexture
    | wgpu.GPUTextureView
    | wgpu.GPUSampler
    | Mapping[str, Any]
)


@dataclass(frozen=True, kw_only=True)
class ShaderTestResult:
    checks: int
    outputs: Mapping[Binding, npt.NDArray[Any]]


class ShaderTestDisabledError(Exception):
    pass


class ShaderAssertionError(AssertionError):
    def __init__(
        self,
        diagnostic: Diagnostic,
        *,
        actual: npt.NDArray[Any],
        expected: npt.NDArray[Any],
        failures: int,
        checks: int,
        tolerance: str,
    ) -> None:
        self.diagnostic = diagnostic
        self.actual = actual
        self.expected = expected
        self.failures = failures
        self.checks = checks
        filename = diagnostic.filename or diagnostic.module or "<shader>"
        lines = [
            (
                f"{filename}:{diagnostic.line}:{diagnostic.column}: "
                f"{diagnostic.message} failed"
            ),
        ]
        if diagnostic.source is not None and diagnostic.line is not None:
            lines.append("    " + diagnostic.source.splitlines()[diagnostic.line - 1])
            lines.append("    " + " " * ((diagnostic.column or 1) - 1) + "^")
        lines.extend((f"actual:   {actual.tolist()}", f"expected: {expected.tolist()}"))
        if tolerance:
            lines.append(tolerance)
        lines.append(f"assertions: {checks}, failures: {failures}")
        super().__init__("\n".join(lines))


class _Resources:
    def __init__(  # noqa: C901, PLR0912
        self, device: wgpu.GPUDevice, resources: Mapping[Binding, Resource]
    ) -> None:
        self.device = device
        self.entries: dict[int, list[dict[str, Any]]] = {}
        self.owned: list[wgpu.GPUBuffer | wgpu.GPUTexture] = []
        self.arrays: dict[
            Binding, tuple[wgpu.GPUBuffer | wgpu.GPUTexture, npt.NDArray[Any]]
        ] = {}
        try:
            for (group, binding), resource in resources.items():
                if isinstance(resource, (Buffer, Texture)):
                    array = np.asarray(resource.data, order="C")
                    if array.dtype.hasobject or not array.dtype.isnative:
                        raise TypeError(  # noqa: TRY301
                            "GPU data must use a native dtype without Python objects"
                        )
                    if not array.nbytes:
                        raise ValueError("GPU data must not be empty")  # noqa: TRY301
                    if isinstance(resource, Buffer):
                        usage = (
                            wgpu.BufferUsage.UNIFORM
                            if resource.uniform
                            else wgpu.BufferUsage.STORAGE
                        )
                        buffer = device.create_buffer_with_data(
                            data=array,
                            usage=usage
                            | wgpu.BufferUsage.COPY_SRC
                            | wgpu.BufferUsage.COPY_DST,
                        )
                        self.owned.append(buffer)
                        self.arrays[group, binding] = buffer, array
                        entry = {"buffer": buffer}
                    else:
                        match resource.dimension, array.ndim:
                            case "1d", 2:
                                size = (array.shape[0], 1, 1)
                            case "2d", 3:
                                size = (array.shape[1], array.shape[0], 1)
                            case "2d" | "3d", 4:
                                size = (array.shape[2], array.shape[1], array.shape[0])
                            case _:
                                raise ValueError(  # noqa: TRY301
                                    "texture data must include spatial axes "
                                    "followed by a channel axis"
                                )
                        usage = (
                            wgpu.TextureUsage.TEXTURE_BINDING
                            | wgpu.TextureUsage.COPY_SRC
                            | wgpu.TextureUsage.COPY_DST
                        )
                        if resource.storage:
                            usage |= wgpu.TextureUsage.STORAGE_BINDING
                        texture = device.create_texture(
                            size=size,
                            dimension=resource.dimension,
                            format=resource.format,
                            usage=usage,
                        )
                        self.owned.append(texture)
                        device.queue.write_texture(
                            {"texture": texture},
                            array,
                            {
                                "bytes_per_row": size[0]
                                * array.shape[-1]
                                * array.itemsize,
                                "rows_per_image": size[1],
                            },
                            size,
                        )
                        self.arrays[group, binding] = texture, array
                        entry = texture.create_view(dimension=resource.view_dimension)
                elif isinstance(resource, wgpu.GPUBuffer):
                    entry = {"buffer": resource}
                elif isinstance(resource, wgpu.GPUTexture):
                    entry = resource.create_view()
                else:
                    entry = resource
                self.entries.setdefault(group, []).append(
                    {"binding": binding, "resource": entry}
                )
        except BaseException:
            self.close()
            raise

    def bind(
        self,
        pipeline: wgpu.GPUComputePipeline | wgpu.GPURenderPipeline,
        encoder: wgpu.GPUComputePassEncoder | wgpu.GPURenderPassEncoder,
    ) -> None:
        for group in range(max(self.entries, default=-1) + 1):
            bind_group = self.device.create_bind_group(
                layout=pipeline.get_bind_group_layout(group),
                entries=self.entries.get(group, []),
            )
            encoder.set_bind_group(group, bind_group)

    def read(self) -> dict[Binding, npt.NDArray[Any]]:
        outputs = {}
        for binding, (resource, array) in self.arrays.items():
            if isinstance(resource, wgpu.GPUBuffer):
                data = self.device.queue.read_buffer(resource)
            else:
                data = self.device.queue.read_texture(
                    {"texture": resource},
                    {
                        "bytes_per_row": resource.width
                        * array.shape[-1]
                        * array.itemsize,
                        "rows_per_image": resource.height,
                    },
                    resource.size,
                )
            outputs[binding] = (
                np.frombuffer(
                    cast("memoryview", data), dtype=array.dtype, count=array.size
                )
                .reshape(array.shape)
                .copy()
            )
        return outputs

    def close(self) -> None:
        for resource in self.owned:
            resource.destroy()
        self.owned.clear()


class ShaderRunner:
    def __init__(self, device: wgpu.GPUDevice) -> None:
        self.device = device

    def compute(
        self,
        shader: CompileResult | str,
        *,
        entry_point: str = "main",
        resources: Mapping[Binding, Resource] | None = None,
        workgroups: int | tuple[int, int, int] = 1,
        constants: Mapping[str, float] | None = None,
    ) -> dict[Binding, npt.NDArray[Any]]:
        __tracebackhide__ = True
        module = self.device.create_shader_module(code=str(shader))
        pipeline = self.device.create_compute_pipeline(
            layout="auto",
            compute={
                "module": module,
                "entry_point": entry_point,
                "constants": {} if constants is None else constants,
            },
        )
        bound = _Resources(self.device, {} if resources is None else resources)
        try:
            encoder = self.device.create_command_encoder()
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(pipeline)
            bound.bind(pipeline, compute_pass)
            compute_pass.dispatch_workgroups(
                *((workgroups, 1, 1) if isinstance(workgroups, int) else workgroups)
            )
            compute_pass.end()
            self.device.queue.submit([encoder.finish()])
            return bound.read()
        finally:
            bound.close()

    def fragment(
        self,
        shader: CompileResult | str,
        *,
        entry_point: str = "main",
        resources: Mapping[Binding, Resource] | None = None,
        size: tuple[int, int] = (1, 1),
        constants: Mapping[str, float] | None = None,
    ) -> npt.NDArray[np.float32]:
        __tracebackhide__ = True
        module = self.device.create_shader_module(code=str(shader))
        vertex = self.device.create_shader_module(
            code="""
            @vertex fn main(
                @builtin(vertex_index) index: u32,
            ) -> @builtin(position) vec4f {
                let positions = array(
                    vec2f(-1.0, -1.0), vec2f(3.0, -1.0), vec2f(-1.0, 3.0),
                );
                return vec4f(positions[index], 0.0, 1.0);
            }
        """
        )
        pipeline = self.device.create_render_pipeline(
            layout="auto",
            vertex={"module": vertex, "entry_point": "main"},
            fragment={
                "module": module,
                "entry_point": entry_point,
                "targets": [{"format": "rgba32float"}],
                "constants": {} if constants is None else constants,
            },
        )
        bound = _Resources(self.device, {} if resources is None else resources)
        target = None
        try:
            target = self.device.create_texture(
                size=(*size, 1),
                format="rgba32float",
                usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
            )
            encoder = self.device.create_command_encoder()
            render_pass = encoder.begin_render_pass(
                color_attachments=[
                    {
                        "view": target.create_view(),
                        "resolve_target": None,
                        "clear_value": (0.0, 0.0, 0.0, 0.0),
                        "load_op": "clear",
                        "store_op": "store",
                    }
                ]
            )
            render_pass.set_pipeline(pipeline)
            bound.bind(pipeline, render_pass)
            render_pass.draw(3)
            render_pass.end()
            self.device.queue.submit([encoder.finish()])
            data = self.device.queue.read_texture(
                {"texture": target},
                {"bytes_per_row": size[0] * 16, "rows_per_image": size[1]},
                (*size, 1),
            )
            return (
                np.frombuffer(cast("memoryview", data), dtype=np.float32)
                .reshape(size[1], size[0], 4)
                .copy()
            )
        finally:
            if target is not None:
                target.destroy()
            bound.close()

    def run_test(
        self,
        modules: Mapping[str, str],
        test_name: str,
        *,
        root: str = "package::main",
        options: CompileOptions | None = None,
        filenames: Mapping[str, str | PathLike[str]] | None = None,
        root_directory: str | PathLike[str] | None = None,
        resources: Mapping[Binding, Resource] | None = None,
        constants: Mapping[str, float] | None = None,
    ) -> ShaderTestResult:
        __tracebackhide__ = True
        copied_resources = {} if resources is None else dict(resources)
        result_binding = 0
        while (0, result_binding) in copied_resources:
            result_binding += 1
        compiled = _native._compile_test(
            modules,
            root,
            test_name,
            CompileOptions() if options is None else options,
            {}
            if filenames is None
            else {name: fspath(path) for name, path in filenames.items()},
            None if root_directory is None else fspath(root_directory),
            result_binding,
        )
        if compiled is None:
            raise ShaderTestDisabledError("WESL conditions disable this test")
        shader, entry_point, sites, overrides = compiled
        copied_resources[0, result_binding] = Buffer(data=np.zeros(16, dtype=np.uint32))
        outputs = self.compute(
            shader,
            entry_point=entry_point,
            resources=copied_resources,
            constants=None
            if constants is None
            else {
                overrides.get(name, name): value for name, value in constants.items()
            },
        )
        result = outputs.pop((0, result_binding))
        if result[0] != 1:
            raise RuntimeError("shader test did not complete")
        if result[2]:
            kind, width = int(result[4]), int(result[5])
            actual, expected = result[8 : 8 + width], result[12 : 12 + width]
            tolerance = ""
            if kind == 0:
                actual, expected = actual.astype(bool), expected.astype(bool)
            elif kind == 2:
                actual, expected = actual.view(np.int32), expected.view(np.int32)
            elif kind in {3, 4}:
                actual, expected = actual.view(np.float32), expected.view(np.float32)
                if kind == 3:
                    relative, absolute = result[6:8].view(np.float32)
                    tolerance = (
                        f"relative tolerance: {relative:g}, "
                        f"absolute tolerance: {absolute:g}"
                    )
                else:
                    tolerance = f"maximum ULP distance: {result[6]}"
            raise ShaderAssertionError(
                sites[int(result[3]) - 1],
                actual=actual,
                expected=expected,
                failures=int(result[2]),
                checks=int(result[1]),
                tolerance=tolerance,
            )
        return ShaderTestResult(checks=int(result[1]), outputs=outputs)
