from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from os import PathLike, fspath
from os.path import relpath
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from . import Diagnostic, TestOptions, _native

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import wgpu

__all__ = [
    "ShaderAssertionError",
    "ShaderTestDisabledError",
    "prepare_test",
    "run_test",
    "run_test_cpu",
]


type _AssertionValue = bool | int | float | tuple[float, ...]


def run_test_cpu(
    modules: Mapping[str, str],
    test_name: str,
    *,
    root: str = "package::main",
    options: TestOptions | None = None,
    filenames: Mapping[str, str | PathLike[str]] | None = None,
    root_directory: str | PathLike[str] | None = None,
    dependencies: Mapping[str, str | PathLike[str]] | None = None,
    constants: Mapping[str, float] | None = None,
) -> None:
    __tracebackhide__ = True
    if options is not None and not isinstance(options, TestOptions):
        message = "options must be TestOptions or None"
        raise TypeError(message)
    compiled = _native.compile_test(
        modules,
        root,
        test_name,
        TestOptions() if options is None else options,
        {}
        if filenames is None
        else {name: fspath(path) for name, path in filenames.items()},
        None if root_directory is None else fspath(root_directory),
        0,
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
        message = "WESL conditions disable this test"
        raise ShaderTestDisabledError(message)
    shader, entry_point, sites, overrides, result_layout = compiled
    data = _native.execute_test_cpu(
        shader,
        entry_point,
        result_layout,
        {}
        if constants is None
        else {
            emitted: value
            for name, value in constants.items()
            if (emitted := overrides.get(name, name)) is not None
        },
    )
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
            failures=result.failures,
            checks=result.checks,
            root_directory=root_directory,
        )


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
    _prepare_test(
        device,
        modules,
        test_name,
        root=root,
        options=options,
        filenames=filenames,
        root_directory=root_directory,
        dependencies=dependencies,
        resources=resources,
        layouts=layouts,
        constants=constants,
    )()


def prepare_test(
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
) -> _PreparedTest:
    __tracebackhide__ = True
    return _prepare_test(
        device,
        modules,
        test_name,
        root=root,
        options=options,
        filenames=filenames,
        root_directory=root_directory,
        dependencies=dependencies,
        resources=resources,
        layouts=layouts,
        constants=constants,
    )


def _prepare_test(
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
    parsed_module: _native.ParsedTestModule | None = None,
) -> _PreparedTest:
    __tracebackhide__ = True
    import wgpu

    if options is not None and not isinstance(options, TestOptions):
        message = "options must be TestOptions or None"
        raise TypeError(message)
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
        parsed_module,
    )
    if compiled is None:
        message = "WESL conditions disable this test"
        raise ShaderTestDisabledError(message)
    shader, entry_point, sites, overrides, result_layout = compiled
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
                device.create_bind_group_layout(entries=layout_groups.get(group, []))
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
                emitted: value
                for name, value in constants.items()
                if (emitted := overrides.get(name, name)) is not None
            },
        },
    )

    return _PreparedTest(
        device,
        pipeline,
        {} if resources is None else resources,
        result_binding,
        result_layout,
        sites,
        root_directory,
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
        failures: int,
        checks: int,
        invocation: int | None = None,
        root_directory: str | PathLike[str] | None = None,
    ) -> None:
        self.diagnostic = diagnostic
        self.actual = actual
        self.expected = expected
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
        if invocation is not None:
            lines.append(f"  invocation: {invocation}")
        lines.extend(("", f"{failures} of {checks} assertions failed"))
        super().__init__("\n".join(lines))


@dataclass
class _PreparedTest:
    device: wgpu.GPUDevice
    pipeline: wgpu.GPUComputePipeline
    resources: Mapping[int, Sequence[dict[str, Any]]]
    result_binding: int
    result_layout: _native.TestLayout
    sites: list[Diagnostic]
    root_directory: str | PathLike[str] | None

    def __call__(
        self,
        *,
        resources: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    ) -> None:
        __tracebackhide__ = True
        import wgpu

        resources = self.resources if resources is None else resources
        groups = {group: list(entries) for group, entries in resources.items()}
        entries = groups.setdefault(0, [])
        result_buffer = self.device.create_buffer(
            size=self.result_layout.buffer_size,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        try:
            entries.append(
                {"binding": self.result_binding, "resource": {"buffer": result_buffer}}
            )
            encoder = self.device.create_command_encoder()
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.pipeline)
            for group in range(min(groups), max(groups) + 1):
                bind_group = self.device.create_bind_group(
                    layout=self.pipeline.get_bind_group_layout(group),
                    entries=groups.get(group, []),
                )
                compute_pass.set_bind_group(group, bind_group)
            compute_pass.dispatch_workgroups(1)
            compute_pass.end()
            self.device.queue.submit([encoder.finish()])
            data = cast("memoryview", self.device.queue.read_buffer(result_buffer))
            result = self.result_layout.decode(data)
            if result.invocations < 1 or result.completed != result.invocations:
                message = "shader test did not complete"
                raise RuntimeError(message)
            if result.passed == 0:
                actual, expected = result.values
                raise ShaderAssertionError(
                    self.sites[result.site - 1],
                    actual=actual,
                    expected=expected,
                    failures=result.failures,
                    checks=result.checks,
                    invocation=result.invocation,
                    root_directory=self.root_directory,
                )
        finally:
            result_buffer.destroy()
