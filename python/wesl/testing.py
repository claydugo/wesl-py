from collections.abc import Mapping, Sequence
from contextlib import suppress
from os import PathLike, fspath
from os.path import relpath
from pathlib import Path
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
    layouts: Mapping[int, Sequence[dict[str, Any]]] | None = None,
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
    if layouts is not None:
        if any(
            group < 0 or group >= device.limits["max-bind-groups"] for group in layouts
        ):
            raise ValueError("layout group index is outside the device's limits")
        bindings.update(entry["binding"] for entry in layouts.get(0, []))
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
    shader, entry_point, sites, overrides, result_layout = compiled
    result_buffer = device.create_buffer(
        size=result_layout.buffer_size,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        module = device.create_shader_module(code=shader)
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
            layout = device.create_pipeline_layout(
                bind_group_layouts=[
                    device.create_bind_group_layout(
                        entries=layout_groups.get(group, [])
                    )
                    for group in range(max(layout_groups) + 1)
                ]
            )
        pipeline = device.create_compute_pipeline(
            layout=layout,
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
        result = result_layout.decode(data)
        if result.completed != 1:
            raise RuntimeError("shader test did not complete")
        if result.passed == 0:
            actual, expected = result.values
            raise ShaderAssertionError(
                sites[result.site - 1],
                actual=actual,
                expected=expected,
                failures=result.failures,
                checks=result.checks,
                root_directory=root_directory,
            )
    finally:
        result_buffer.destroy()
