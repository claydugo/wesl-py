from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import replace
from os.path import relpath
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, cast

from . import Diagnostic, TestOptions, _native
from ._constants import add_constant_modules
from ._resources import module_name
from .reflect import _decode, _Decoded

if TYPE_CHECKING:
    from collections.abc import Sequence
    from os import PathLike
    from typing import SupportsFloat

    import numpy.typing as npt
    import wgpu

    from . import Compiler

__all__ = [
    "ShaderAssertionError",
    "ShaderTestDisabledError",
    "run_compute",
    "run_test",
    "run_test_cpu",
]


type _AssertionValue = bool | int | float | tuple[bool | int | float, ...]


def _test_compiler(
    compiler: Compiler,
    root: str,
    source: str | None,
    constants: Mapping[str, SupportsFloat | str] | None,
) -> tuple[Compiler, str]:
    modules = dict(compiler.modules)
    filenames = compiler.filenames
    if root.endswith((".wesl", ".wgsl")):
        path = PurePosixPath(root.removeprefix("./"))
        root = module_name(
            (*path.parent.parts, path.stem.replace(".", "_")), namespace="package"
        )
        if source is None and compiler.root_directory is not None:
            filename = Path(compiler.root_directory) / path
            source = filename.read_text(encoding="utf-8")
            filenames = {**filenames, root: filename}
    if source is not None:
        modules[root] = source
    if constants:
        modules = add_constant_modules(modules, {"constants": constants})
    return replace(compiler, modules=modules, filenames=filenames), root


def _compute_pipeline(
    device: wgpu.GPUDevice,
    layout: wgpu.GPUPipelineLayout | str,
    shader: str,
    entry_point: str,
    names: Mapping[str, str],
) -> wgpu.GPUComputePipeline:
    __tracebackhide__ = True
    import wgpu

    try:
        return device.create_compute_pipeline(
            layout=layout,
            compute={
                "module": device.create_shader_module(code=shader),
                "entry_point": entry_point,
            },
        )
    except wgpu.GPUError as error:
        message = str(error)
        if names:
            pattern = re.compile(rf"\b(?:{'|'.join(map(re.escape, names))})\b")
            message = "\n".join(
                line
                if "\u2502" in line
                else pattern.sub(lambda match: names[match[0]], line)
                for line in message.splitlines()
            )
        raise type(error)(message) from None


def run_test_cpu(
    compiler: Compiler,
    test_name: str,
    *,
    source: str | None = None,
    root: str = "package::main",
    options: TestOptions | None = None,
    constants: Mapping[str, SupportsFloat | str] | None = None,
) -> None:
    __tracebackhide__ = True
    if options is not None and not isinstance(options, TestOptions):
        message = "options must be TestOptions or None"
        raise TypeError(message)
    compiler, root = _test_compiler(compiler, root, source, constants)
    compiled = _native.compile_test(
        compiler, root, test_name, TestOptions() if options is None else options, 0, []
    )
    if compiled is None:
        message = "WESL conditions disable this test"
        raise ShaderTestDisabledError(message)
    shader, entry_point, sites, _, result_layout = compiled
    data = _native.execute_test_cpu(shader, entry_point, result_layout)
    result = result_layout.decode(bytes(data))
    if result.completed != 1:
        message = "shader test did not complete"
        raise RuntimeError(message)
    if result.passed == 0:
        actual, expected = result.values
        raise ShaderAssertionError(
            sites[result.site - 1],
            actual=actual,
            expected=expected,
            value_type=result.value_type,
            failures=result.failures,
            checks=result.checks,
            root_directory=compiler.root_directory,
        )


def run_test(
    device: wgpu.GPUDevice,
    compiler: Compiler,
    test_name: str,
    *,
    source: str | None = None,
    root: str = "package::main",
    options: TestOptions | None = None,
    resources: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    layouts: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    constants: Mapping[str, SupportsFloat | str] | None = None,
) -> None:
    __tracebackhide__ = True
    _run_test(
        device,
        compiler,
        test_name,
        source=source,
        root=root,
        options=options,
        resources=resources,
        layouts=layouts,
        constants=constants,
    )


def _fill_buffer(target: _Decoded, value: npt.ArrayLike | Mapping[str, Any]) -> None:
    import numpy as np

    pending: list[tuple[_Decoded, Any]] = [(target, value)]
    while pending:
        target, assigned = pending.pop()
        if isinstance(target, dict):
            names = (
                set(assigned.dtype.names or ())
                if isinstance(assigned, np.ndarray)
                else set(assigned)
            )
            if names != target.keys():
                message = (
                    f"a structure value needs the members {sorted(target)}, "
                    f"got {sorted(names)}"
                )
                raise ValueError(message)
            pending.extend((target[name], assigned[name]) for name in target)
            continue
        assigned = np.asarray(assigned)
        if (assigned.dtype.kind in "fcOUS" and target.dtype.kind in "biu") or (
            assigned.dtype.kind in "cOUS" and target.dtype.kind == "f"
        ):
            message = (
                f"cannot fill a {target.dtype} buffer with {assigned.dtype} values;"
                " convert them first"
            )
            raise TypeError(message)
        target[...] = assigned


def run_compute(
    device: wgpu.GPUDevice,
    compiler: Compiler,
    source: str | None = None,
    *,
    root: str = "package::main",
    constants: Mapping[str, SupportsFloat | str] | None = None,
    buffers: Mapping[str, npt.ArrayLike | Mapping[str, Any]] | None = None,
    dispatch_workgroups: int | tuple[int, int, int] = 1,
) -> dict[str, _Decoded]:
    __tracebackhide__ = True
    import numpy as np
    import wgpu

    compiler, root = _test_compiler(compiler, root, source, constants)
    shader, declared, names = _native.compile_compute(compiler, root)
    if not declared:
        message = "run_compute requires a @buffer variable for its results"
        raise ValueError(message)
    inputs = (
        {}
        if buffers is None
        else {
            name: value if isinstance(value, Mapping) else np.asarray(value)
            for name, value in buffers.items()
        }
    )
    if unknown := sorted(inputs.keys() - {buffer["name"] for buffer in declared}):
        message = f"no @buffer variable is named {', '.join(unknown)}"
        raise ValueError(message)
    if undecodable := [
        buffer["name"]
        for buffer in declared
        if buffer["layout"] is None
        and (buffer["access"] == "read_write" or buffer["name"] in inputs)
    ]:
        message = (
            f"cannot decode @buffer {', '.join(undecodable)}: wesl-py has no NumPy "
            "layout for a bool or for a structure that ends in a runtime-sized array"
        )
        raise TypeError(message)
    sizes = []
    contents = []
    for buffer in declared:
        size = buffer["size"]
        layout = buffer["layout"]
        value = inputs.get(buffer["name"])
        if value is not None and layout[0] == "array" and layout[2] is None:
            leaf = value
            while isinstance(leaf, Mapping):
                leaf = next(iter(leaf.values()))
            size = max(size, len(leaf) * layout[3])
        data = bytearray(np.full(-(-size // 4), -999.0, dtype="<f4").tobytes())
        if value is not None:
            _fill_buffer(_decode(layout, data, size), value)
        sizes.append(size)
        contents.append(data)
    layout = device.create_bind_group_layout(
        entries=[
            {
                "binding": buffer["binding"],
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {
                    "type": "storage"
                    if buffer["access"] == "read_write"
                    else "read-only-storage"
                },
            }
            for buffer in declared
        ]
    )
    pipeline = _compute_pipeline(
        device,
        device.create_pipeline_layout(bind_group_layouts=[layout]),
        shader,
        "main",
        names,
    )
    created = [
        device.create_buffer_with_data(
            data=data,
            usage=wgpu.BufferUsage.STORAGE
            | wgpu.BufferUsage.COPY_SRC
            | wgpu.BufferUsage.COPY_DST,
        )
        for data in contents
    ]
    try:
        encoder = device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        compute_pass.set_bind_group(
            0,
            device.create_bind_group(
                layout=layout,
                entries=[
                    {"binding": buffer["binding"], "resource": {"buffer": storage}}
                    for buffer, storage in zip(declared, created, strict=True)
                ],
            ),
        )
        compute_pass.dispatch_workgroups(
            *(
                (dispatch_workgroups, 1, 1)
                if isinstance(dispatch_workgroups, int)
                else dispatch_workgroups
            )
        )
        compute_pass.end()
        device.queue.submit([encoder.finish()])
        return {
            buffer["name"]: _decode(
                buffer["layout"],
                bytearray(cast("memoryview", device.queue.read_buffer(storage))),
                size,
            )
            for buffer, storage, size in zip(declared, created, sizes, strict=True)
            if buffer["access"] == "read_write"
        }
    finally:
        for storage in created:
            storage.destroy()


def _run_test(
    device: wgpu.GPUDevice,
    compiler: Compiler,
    test_name: str,
    *,
    source: str | None = None,
    root: str = "package::main",
    options: TestOptions | None = None,
    resources: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    layouts: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    constants: Mapping[str, SupportsFloat | str] | None = None,
    parsed_module: _native.ParsedTestModule | None = None,
) -> None:
    __tracebackhide__ = True
    import wgpu

    if options is not None and not isinstance(options, TestOptions):
        message = "options must be TestOptions or None"
        raise TypeError(message)
    compiler, root = _test_compiler(compiler, root, source, constants)
    entries = [] if resources is None else resources.get(0, [])
    bindings = {entry["binding"] for entry in entries}
    if layouts is not None:
        if any(
            group < 0 or group >= device.limits["max-bind-groups"] for group in layouts
        ):
            message = "layout group index is outside the device's limits"
            raise ValueError(message)
        bindings.update(entry["binding"] for entry in layouts.get(0, []))
    result_binding = 0
    while result_binding in bindings:
        result_binding += 1
    compiled = _native.compile_test(
        compiler,
        root,
        test_name,
        TestOptions() if options is None else options,
        result_binding,
        sorted(bindings),
        parsed_module,
    )
    if compiled is None:
        message = "WESL conditions disable this test"
        raise ShaderTestDisabledError(message)
    shader, entry_point, sites, names, result_layout = compiled
    layout: wgpu.GPUPipelineLayout | str = "auto"
    if layouts is not None:
        layout_groups = {group: list(entries) for group, entries in layouts.items()}
        layout_groups.setdefault(0, []).append(
            {
                "binding": result_binding,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {
                    "type": "storage",
                    "min_binding_size": result_layout.buffer_size,
                },
            }
        )
        layout_groups[0].extend(
            {
                "binding": buffer["binding"],
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {
                    "type": "storage"
                    if buffer["access"] == "read_write"
                    else "read-only-storage"
                },
            }
            for buffer in result_layout.buffers
        )
        layout = device.create_pipeline_layout(
            bind_group_layouts=[
                device.create_bind_group_layout(entries=layout_groups.get(group, []))
                for group in range(max(layout_groups) + 1)
            ]
        )
    _dispatch_test(
        device,
        _compute_pipeline(device, layout, shader, entry_point, names),
        resources={} if resources is None else resources,
        result_binding=result_binding,
        result_layout=result_layout,
        sites=sites,
        root_directory=compiler.root_directory,
        automatic_layout=layouts is None,
    )


class ShaderTestDisabledError(Exception):
    pass


class ShaderAssertionError(AssertionError):
    def __init__(
        self,
        diagnostic: Diagnostic,
        *,
        actual: _AssertionValue,
        expected: _AssertionValue,
        value_type: str,
        failures: int,
        checks: int,
        invocation: int | None = None,
        root_directory: str | PathLike[str] | None = None,
    ) -> None:
        self.diagnostic = diagnostic
        self.actual = actual
        self.expected = expected
        self.value_type = value_type
        self.failures = failures
        self.checks = checks
        self.invocation = invocation
        filename = diagnostic.filename or diagnostic.module or "<shader>"
        if diagnostic.filename is not None and Path(filename).is_absolute():
            with suppress(ValueError):
                filename = relpath(filename, root_directory)
        self.filename = filename
        message = f"{diagnostic.message} failed"
        if failures > 1:
            message += " (first failure)"
        lines = _native.render_diagnostic(
            Diagnostic(
                message,
                module=diagnostic.module,
                filename=filename if diagnostic.filename is not None else None,
                source=diagnostic.source,
                span=diagnostic.span,
            )
        ).splitlines()
        lines.append("")
        suffix = (
            "u"
            if value_type in {"u32", "vec2u", "vec3u", "vec4u"}
            else "i"
            if value_type in {"i32", "vec2i", "vec3i", "vec4i"}
            else ""
        )
        for label, value in (("actual:", actual), ("expected:", expected)):
            components = value if isinstance(value, tuple) else (value,)
            formatted = ", ".join(
                str(component).lower()
                if isinstance(component, bool)
                else f"{component}{suffix}"
                if isinstance(component, int)
                else repr(component)
                for component in components
            )
            if isinstance(value, tuple):
                formatted = f"{value_type}({formatted})"
            lines.append(f"  {label:<9} {formatted}")
        if invocation is not None:
            lines.append(f"  invocation: {invocation}")
        lines.extend(("", f"{failures} of {checks} assertions failed"))
        super().__init__("\n".join(lines))


def _dispatch_test(
    device: wgpu.GPUDevice,
    pipeline: wgpu.GPUComputePipeline,
    *,
    resources: Mapping[int, Sequence[dict[str, Any]]],
    result_binding: int,
    result_layout: _native.TestLayout,
    sites: list[Diagnostic],
    root_directory: str | PathLike[str] | None,
    automatic_layout: bool,
) -> None:
    __tracebackhide__ = True
    import wgpu

    reached = set(result_layout.resources)
    groups = {
        group: [
            entry
            for entry in entries
            if not automatic_layout or (group, entry["binding"]) in reached
        ]
        for group, entries in resources.items()
    }
    groups = {
        group: entries for group, entries in groups.items() if entries or group == 0
    }
    entries = groups.setdefault(0, [])
    result_buffer = device.create_buffer(
        size=result_layout.buffer_size,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    scratch = [
        device.create_buffer(
            size=buffer["size"],
            usage=wgpu.BufferUsage.STORAGE
            | wgpu.BufferUsage.COPY_SRC
            | wgpu.BufferUsage.COPY_DST,
        )
        for buffer in result_layout.buffers
    ]
    try:
        entries.append(
            {"binding": result_binding, "resource": {"buffer": result_buffer}}
        )
        entries.extend(
            {"binding": buffer["binding"], "resource": {"buffer": created}}
            for buffer, created in zip(result_layout.buffers, scratch, strict=True)
        )
        encoder = device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        for group in range(min(groups), max(groups) + 1):
            bind_group = device.create_bind_group(
                layout=pipeline.get_bind_group_layout(group),
                entries=groups.get(group, []),
            )
            compute_pass.set_bind_group(group, bind_group)
        compute_pass.dispatch_workgroups(1)
        compute_pass.end()
        device.queue.submit([encoder.finish()])
        data = cast("memoryview", device.queue.read_buffer(result_buffer))
        result = result_layout.decode(data)
        if result.invocations < 1 or result.completed != result.invocations:
            message = "shader test did not complete"
            raise RuntimeError(message)
        if result.passed == 0:
            actual, expected = result.values
            raise ShaderAssertionError(
                sites[result.site - 1],
                actual=actual,
                expected=expected,
                value_type=result.value_type,
                failures=result.failures,
                checks=result.checks,
                invocation=result.invocation,
                root_directory=root_directory,
            )
    finally:
        result_buffer.destroy()
        for created in scratch:
            created.destroy()
