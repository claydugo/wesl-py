from collections.abc import Mapping, Sequence
from contextlib import suppress
from os import PathLike, fspath
from os.path import relpath
from pathlib import Path
from struct import unpack_from
from typing import Any, cast

import wgpu

from . import Diagnostic, TestOptions, _native
from ._project import ProjectDependencies

__all__ = [
    "ShaderAssertionError",
    "ShaderTestDisabledError",
    "run_test",
]


type _AssertionValue = bool | int | float | tuple[float, ...]


class ShaderTestDisabledError(Exception):
    pass


class ShaderAssertionError(AssertionError):
    def __init__(
        self,
        diagnostic: Diagnostic,
        *,
        actual: _AssertionValue,
        expected: _AssertionValue,
        failures: int,
        checks: int,
        root_directory: str | PathLike[str] | None = None,
    ) -> None:
        self.diagnostic = diagnostic
        self.actual = actual
        self.expected = expected
        self.failures = failures
        self.checks = checks
        filename = diagnostic.filename or diagnostic.module or "<shader>"
        if diagnostic.filename is not None and Path(filename).is_absolute():
            with suppress(ValueError):
                filename = relpath(filename, root_directory)
        self.filename = filename
        location = ":".join(
            str(part)
            for part in (filename, diagnostic.line, diagnostic.column)
            if part is not None
        )
        lines = [f"{location}: {diagnostic.message} failed"]
        if failures > 1:
            lines[0] += " (first failure)"
        if diagnostic.source is not None and diagnostic.line is not None:
            source = diagnostic.source.splitlines()
            end_line = diagnostic.end_line or diagnostic.line
            if end_line > diagnostic.line and diagnostic.end_column == 1:
                end_line -= 1
            width = len(str(end_line))
            lines.append(f"{'':>{width}} |")
            for line_number in range(diagnostic.line, end_line + 1):
                source_line = source[line_number - 1]
                start = (
                    (diagnostic.column or 1) - 1
                    if line_number == diagnostic.line
                    else len(source_line) - len(source_line.lstrip())
                )
                end = (
                    (diagnostic.end_column or start + 2) - 1
                    if line_number == diagnostic.end_line
                    else len(source_line)
                )
                offset = len(source_line[:start].expandtabs(4))
                length = max(1, len(source_line[:end].expandtabs(4)) - offset)
                lines.append(f"{line_number:>{width}} | {source_line.expandtabs(4)}")
                lines.append(f"{'':>{width}} | {' ' * offset}{'^' * length}")
        lines.append("")
        for label, value in (("actual:", actual), ("expected:", expected)):
            if isinstance(value, tuple):
                formatted = f"vec{len(value)}f({', '.join(map(repr, value))})"
            elif isinstance(value, bool):
                formatted = str(value).lower()
            elif isinstance(value, int):
                formatted = f"{value}u"
            else:
                formatted = repr(value)
            lines.append(f"  {label:<9} {formatted}")
        lines.extend(("", f"{failures} of {checks} assertions failed"))
        super().__init__("\n".join(lines))


def run_test(
    device: wgpu.GPUDevice,
    modules: Mapping[str, str],
    test_name: str,
    *,
    root: str = "package::main",
    options: TestOptions | None = None,
    filenames: Mapping[str, str | PathLike[str]] | None = None,
    root_directory: str | PathLike[str] | None = None,
    dependencies: Mapping[str, str | PathLike[str]] | None = None,
    resources: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    constants: Mapping[str, float] | None = None,
) -> None:
    __tracebackhide__ = True
    if options is not None and not isinstance(options, TestOptions):
        raise TypeError("options must be TestOptions or None")
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
        TestOptions() if options is None else options,
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
        dependencies.aliases if isinstance(dependencies, ProjectDependencies) else None,
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
        passed, failures, value_kind, components, site, completed, checks = unpack_from(
            "<IIII32xIII", data
        )
        if completed != 1:
            raise RuntimeError("shader test did not complete")
        if passed == 0:
            actual: _AssertionValue
            expected: _AssertionValue
            if value_kind == 0:
                actual = bool(unpack_from("<I", data, 16)[0])
                expected = bool(unpack_from("<I", data, 32)[0])
            elif value_kind == 1:
                actual = unpack_from("<I", data, 16)[0]
                expected = unpack_from("<I", data, 32)[0]
            else:
                actual = unpack_from(f"<{components}f", data, 16)
                expected = unpack_from(f"<{components}f", data, 32)
                if components == 1:
                    actual = actual[0]
                    expected = expected[0]
            raise ShaderAssertionError(
                sites[site - 1],
                actual=actual,
                expected=expected,
                failures=failures,
                checks=checks,
                root_directory=root_directory,
            )
    finally:
        result_buffer.destroy()
