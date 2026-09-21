from collections.abc import Mapping, Sequence
from os import PathLike, fspath
from pathlib import Path
from struct import unpack_from
from typing import Any, cast

import wgpu

from . import CompileOptions, Diagnostic, _native

__all__ = [
    "ShaderAssertionError",
    "ShaderTestDisabledError",
    "run_test",
]


class ShaderTestDisabledError(Exception):
    pass


class ShaderAssertionError(AssertionError):
    def __init__(
        self,
        diagnostic: Diagnostic,
        *,
        actual: tuple[float, ...],
        expected: tuple[float, ...],
        failures: int,
        checks: int,
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
        lines.extend((f"actual:   {actual}", f"expected: {expected}"))
        lines.append(f"assertions: {checks}, failures: {failures}")
        super().__init__("\n".join(lines))


def run_test(
    device: wgpu.GPUDevice,
    modules: Mapping[str, str],
    test_name: str,
    *,
    root: str = "package::main",
    options: CompileOptions | None = None,
    filenames: Mapping[str, str | PathLike[str]] | None = None,
    root_directory: str | PathLike[str] | None = None,
    dependencies: Mapping[str, str | PathLike[str]] | None = None,
    resources: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    constants: Mapping[str, float] | None = None,
) -> None:
    __tracebackhide__ = True
    groups = (
        {}
        if resources is None
        else {group: list(entries) for group, entries in resources.items()}
    )
    entries = groups.setdefault(0, [])
    bindings = {entry["binding"] for entry in entries}
    result_binding = 0
    while result_binding in bindings:
        result_binding += 1
    compiled = _native.compile_test(
        modules,
        root,
        test_name,
        CompileOptions() if options is None else options,
        {}
        if filenames is None
        else {name: fspath(path) for name, path in filenames.items()},
        None if root_directory is None else fspath(root_directory),
        result_binding,
        {
            "wgsl_test": str(Path(__file__).parent / "shaders/wgsl_test"),
            **(
                {}
                if dependencies is None
                else {name: fspath(path) for name, path in dependencies.items()}
            ),
        },
    )
    if compiled is None:
        raise ShaderTestDisabledError("WESL conditions disable this test")
    shader, entry_point, sites, overrides = compiled
    result_buffer = device.create_buffer(
        size=64,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        module = device.create_shader_module(code=shader)
        pipeline = device.create_compute_pipeline(
            layout="auto",
            compute={
                "module": module,
                "entry_point": entry_point,
                "constants": {}
                if constants is None
                else {
                    overrides.get(name, name): value
                    for name, value in constants.items()
                },
            },
        )
        entries.append(
            {"binding": result_binding, "resource": {"buffer": result_buffer}}
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
        passed, failures, site, completed, checks = unpack_from("<II40xIII", data)
        if completed != 1:
            raise RuntimeError("shader test did not complete")
        if passed == 0:
            raise ShaderAssertionError(
                sites[site - 1],
                actual=unpack_from("<4f", data, 16),
                expected=unpack_from("<4f", data, 32),
                failures=failures,
                checks=checks,
            )
    finally:
        result_buffer.destroy()
