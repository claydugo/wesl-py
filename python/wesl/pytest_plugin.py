from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from . import (
    CompileError,
    CompileOptions,
    Compiler,
    Diagnostic,
    _native,
    compile_source,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    import wgpu

    from .testing import Binding, Resource, ShaderRunner


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("wesl")
    group.addoption(
        "--wesl-gpu",
        choices=("required", "optional"),
        default="required",
        help="Fail or skip shader tests when no GPU adapter is available",
    )
    parser.addini(
        "wesl_files",
        "Patterns for WESL test files",
        type="args",
        default=["test_*.wesl", "*_test.wesl", "*.test.wesl"],
    )
    parser.addini(
        "wesl_root",
        "Shader package directory relative to pytest's root directory",
        default=".",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "wesl: executes a WESL shader test")


@pytest.hookimpl(tryfirst=True)
def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if isinstance(metafunc.definition.parent, WeslModule):
        setattr(metafunc.module, metafunc.definition.name, metafunc.function)


def pytest_collect_file(
    file_path: Path, parent: pytest.Collector
) -> pytest.Module | None:
    if file_path.suffix == ".wesl" and (
        any(file_path.match(pattern) for pattern in parent.config.getini("wesl_files"))
        or parent.session.isinitpath(file_path)
    ):
        return WeslModule.from_parent(parent, path=file_path)
    return None


class WeslModule(pytest.Module):
    def collect(self) -> Iterator[pytest.Item | pytest.Collector]:
        source = self.path.read_text(encoding="utf-8")
        self.source = source
        try:
            tests = _native._discover_tests(source, str(self.path))
        except CompileError as error:
            raise self.CollectError(str(error)) from error
        module = ModuleType(self.path.stem)
        module.__file__ = str(self.path)
        self.obj = module
        self.locations = {}
        collected = set()
        for name, start, end in tests:
            if name in collected:
                continue
            collected.add(name)

            def run_shader(
                *,
                wesl_runner: ShaderRunner,
                wesl_compiler: Compiler,
                wesl_resources: Mapping[Binding, Resource],
                wesl_constants: Mapping[str, float],
                shader_path: Path = self.path,
                shader_source: str = source,
                shader_name: str = name,
            ) -> None:
                __tracebackhide__ = True
                from .testing import ShaderTestDisabledError

                root_directory = (
                    shader_path.parent
                    if wesl_compiler.root_directory is None
                    else Path(wesl_compiler.root_directory).absolute()
                )
                relative = shader_path.relative_to(root_directory)
                parts = (*relative.parts[:-1], relative.stem.replace(".", "_"))
                root = "package::" + "::".join(parts)
                if root in wesl_compiler.modules:
                    raise ValueError(
                        "the test module is already present in wesl_modules"
                    )
                try:
                    wesl_runner.run_test(
                        {**wesl_compiler.modules, root: shader_source},
                        shader_name,
                        root=root,
                        options=wesl_compiler.options,
                        filenames={**wesl_compiler.filenames, root: shader_path},
                        root_directory=root_directory,
                        resources=wesl_resources,
                        constants=wesl_constants,
                    )
                except ShaderTestDisabledError as error:
                    pytest.skip(str(error))

            diagnostic = Diagnostic("", source=source, span=(start, end))
            self.locations[name] = (diagnostic.line or 1) - 1
            run_shader.__name__ = name
            run_shader.__module__ = module.__name__
            vars(run_shader)["__test__"] = True
            pytest.mark.wesl(run_shader)
            try:
                items = self.ihook.pytest_pycollect_makeitem(
                    collector=self, name=name, obj=run_shader
                )
            finally:
                vars(module).pop(name, None)
            if items is None:
                continue
            for item in items if isinstance(items, list) else [items]:
                if isinstance(item, pytest.Function):
                    shader = WeslTest(item, self, name)
                    item.setup = shader.setup
                    item.reportinfo = shader.reportinfo
                    item.repr_failure = shader.repr_failure
                yield item


class WeslTest:
    def __init__(self, item: pytest.Function, module: WeslModule, name: str) -> None:
        self.item = item
        self.module = module
        self.name = name
        self.setup_item = item.setup
        self.repr_item_failure = item.repr_failure

    def reportinfo(self) -> tuple[Path, int, str]:
        return self.item.path, self.module.locations[self.name], self.item.name

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException]):  # noqa: ANN201
        style = self.item.config.getoption("tbstyle")
        if (
            style == "native"
            or self.item.config.getoption("fulltrace")
            or "wesl.testing" not in sys.modules
        ):
            return self.repr_item_failure(excinfo)
        from .testing import ShaderAssertionError

        if not isinstance(excinfo.value, ShaderAssertionError):
            return self.repr_item_failure(excinfo)
        representation = excinfo.getrepr(
            style="line" if style == "line" else "value",
            tbfilter=False,
            chain=style != "line",
        )
        if style == "line":
            entry = representation.reprtraceback.reprentries[-1]
            entry.lines = entry.lines[:1]
        if representation.reprcrash is not None:
            diagnostic = excinfo.value.diagnostic
            representation.reprcrash.path = (
                diagnostic.filename or diagnostic.module or str(self.item.path)
            )
            representation.reprcrash.lineno = diagnostic.line or 1
            representation.reprcrash.message = f"{diagnostic.message} failed"
        return representation

    def setup(self) -> None:
        compiler = self.item._request.getfixturevalue("wesl_compiler")
        source = compile_source(
            self.module.source,
            options=replace(
                compiler.options,
                imports=False,
                strip=False,
                lower=False,
                validate=False,
                mangle_root=False,
            ),
        )
        tests = _native._discover_tests(str(source), str(self.item.path))
        if not any(name == self.name for name, _, _ in tests):
            pytest.skip("WESL conditions disable this test")
        self.setup_item()


@pytest.fixture(scope="session")
def wesl_device(request: pytest.FixtureRequest) -> Iterator[wgpu.GPUDevice]:
    try:
        import wgpu
    except ModuleNotFoundError:
        if request.config.getoption("--wesl-gpu") == "optional":
            pytest.skip("install wesl-py[testing] to run GPU tests")
        pytest.fail("install wesl-py[testing] to run GPU tests", pytrace=False)
    try:
        adapter = wgpu.gpu.request_adapter_sync()
    except RuntimeError as error:
        if request.config.getoption("--wesl-gpu") == "optional":
            pytest.skip(str(error))
        pytest.fail(f"no GPU adapter is available: {error}", pytrace=False)
    device = adapter.request_device_sync()
    yield device
    device.destroy()


@pytest.fixture
def wesl_compiler(
    wesl_options: CompileOptions,
    wesl_modules: Mapping[str, str],
    wesl_filenames: Mapping[str, str | Path],
    wesl_root_directory: Path,
) -> Compiler:
    return Compiler(
        options=wesl_options,
        modules=wesl_modules,
        filenames=wesl_filenames,
        root_directory=wesl_root_directory,
    )


@pytest.fixture
def wesl_runner(wesl_device: wgpu.GPUDevice) -> ShaderRunner:
    from .testing import ShaderRunner

    return ShaderRunner(wesl_device)


@pytest.fixture
def wesl_resources() -> Mapping[Binding, Resource]:
    return {}


@pytest.fixture
def wesl_modules() -> Mapping[str, str]:
    return {}


@pytest.fixture
def wesl_filenames() -> Mapping[str, str | Path]:
    return {}


@pytest.fixture
def wesl_options() -> CompileOptions:
    return CompileOptions()


@pytest.fixture
def wesl_constants() -> Mapping[str, float]:
    return {}


@pytest.fixture
def wesl_root_directory(pytestconfig: pytest.Config) -> Path:
    return (pytestconfig.rootpath / pytestconfig.getini("wesl_root")).resolve()
