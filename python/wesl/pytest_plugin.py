from __future__ import annotations

import sys
from collections.abc import Mapping
from os.path import abspath
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from . import (
    CompileError,
    CompileOptions,
    Compiler,
    Diagnostic,
    Features,
    TestOptions,
    _native,
)
from ._project import load_project
from ._resources import module_name

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import Any

    import wgpu
    from _pytest._code.code import TerminalRepr

    from . import Feature
    from ._project import Project


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("wesl")
    group.addoption(
        "--wesl-gpu",
        choices=("required", "optional"),
        default="required",
        help="Fail or skip shader tests when no WebGPU adapter is available",
    )
    parser.addini(
        "wesl_root",
        "Shader package directory relative to pytest's root directory",
        default="",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "wesl: executes a WESL shader test")
    config.addinivalue_line(
        "markers", "gpu: requires a WebGPU adapter (hardware or software)"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if isinstance(metafunc.definition.parent, WeslModule):
        setattr(metafunc.module, metafunc.definition.name, metafunc.function)


def pytest_collect_file(
    file_path: Path, parent: pytest.Collector
) -> pytest.Module | None:
    if file_path.suffix == ".wesl" and (
        file_path.name.endswith(".test.wesl") or parent.session.isinitpath(file_path)
    ):
        return WeslModule.from_parent(parent, path=file_path)
    return None


class WeslModule(pytest.Module):
    def collect(self) -> Iterator[pytest.Item | pytest.Collector]:
        source = self.path.read_text(encoding="utf-8")
        try:
            parsed_module = _native.ParsedTestModule(source, str(self.path))
            tests = parsed_module.tests
        except CompileError as error:
            raise self.CollectError(str(error)) from error
        module = ModuleType(self.path.stem)
        module.__file__ = str(self.path)
        self.obj = module
        self.locations = {}
        for name, start, end in tests:
            if name in self.locations:
                continue

            def run_shader(
                *,
                wesl_device: wgpu.GPUDevice,
                wesl_test_options: TestOptions,
                wesl_modules: Mapping[str, str],
                wesl_filenames: Mapping[str, str | Path],
                wesl_root_directory: Path,
                wesl_dependencies: Mapping[str, str | Path],
                wesl_resources: Mapping[int, Sequence[dict[str, Any]]],
                wesl_layouts: Mapping[int, Sequence[dict[str, Any]]] | None,
                wesl_constants: Mapping[str, float],
                shader_path: Path = self.path,
                shader_source: str = source,
                shader_name: str = name,
                shader_module: _native.ParsedTestModule = parsed_module,
            ) -> None:
                __tracebackhide__ = True
                from .testing import ShaderTestDisabledError, _prepare_test

                root_directory = Path(abspath(wesl_root_directory))
                relative = shader_path.relative_to(root_directory)
                parts = (*relative.parts[:-1], relative.stem.replace(".", "_"))
                root = module_name(parts, namespace="package")
                if root in wesl_modules:
                    message = "the test module is already present in wesl_modules"
                    raise ValueError(message)
                try:
                    _prepare_test(
                        wesl_device,
                        {**wesl_modules, root: shader_source},
                        shader_name,
                        root=root,
                        options=wesl_test_options,
                        filenames={**wesl_filenames, root: shader_path},
                        root_directory=root_directory,
                        dependencies=wesl_dependencies,
                        resources=wesl_resources,
                        layouts=wesl_layouts,
                        constants=wesl_constants,
                        parsed_module=shader_module,
                    )()
                except ShaderTestDisabledError as error:
                    pytest.skip(str(error))

            diagnostic = Diagnostic("", source=source, span=(start, end))
            self.locations[name] = (diagnostic.line or 1) - 1
            run_shader.__name__ = name
            run_shader.__module__ = module.__name__
            vars(run_shader)["__test__"] = True
            pytest.mark.wesl(run_shader)
            pytest.mark.gpu(run_shader)
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
                    item.reportinfo = shader.reportinfo
                    vars(item).pop("location", None)
                    item.repr_failure = shader.repr_failure
                yield item


class WeslTest:
    def __init__(self, item: pytest.Function, module: WeslModule, name: str) -> None:
        self.item = item
        self.module = module
        self.name = name
        self.repr_item_failure = item.repr_failure

    def reportinfo(self) -> tuple[Path, int, str]:
        return self.item.path, self.module.locations[self.name], self.item.name

    def repr_failure(
        self, excinfo: pytest.ExceptionInfo[BaseException]
    ) -> str | TerminalRepr:
        style = self.item.config.getoption("tbstyle")
        if (
            style == "native"
            or self.item.config.getoption("fulltrace")
            or "wesl.testing" not in sys.modules
        ):
            return self.repr_item_failure(excinfo)
        from .testing import ShaderAssertionError

        if (
            not isinstance(excinfo.value, ShaderAssertionError)
            or excinfo.value.__cause__ is not None
            or (
                excinfo.value.__context__ is not None
                and not excinfo.value.__suppress_context__
            )
        ):
            return self.repr_item_failure(excinfo)
        error = ShaderAssertionError(
            excinfo.value.diagnostic,
            actual=excinfo.value.actual,
            expected=excinfo.value.expected,
            failures=excinfo.value.failures,
            checks=excinfo.value.checks,
            invocation=excinfo.value.invocation,
            root_directory=self.item.config.rootpath,
        )
        if style == "line":
            diagnostic = error.diagnostic
            return (
                f"{error.filename}:{diagnostic.line or 1}:"
                f"{diagnostic.column or 1}: {diagnostic.message} failed"
            )
        return "\n".join((str(error), *getattr(excinfo.value, "__notes__", ())))


@pytest.fixture(scope="session")
def wesl_device(request: pytest.FixtureRequest) -> Iterator[wgpu.GPUDevice]:
    try:
        import wgpu
    except ModuleNotFoundError as error:
        if error.name != "wgpu":
            raise
        if request.config.getoption("--wesl-gpu") == "optional":
            pytest.skip("install wesl-py[testing] to run shader tests")
        pytest.fail("install wesl-py[testing] to run shader tests", pytrace=False)
    try:
        adapter = wgpu.gpu.request_adapter_sync()
    except RuntimeError as error:
        if request.config.getoption("--wesl-gpu") == "optional":
            pytest.skip(str(error))
        pytest.fail(f"no WebGPU adapter is available: {error}", pytrace=False)
    device = adapter.request_device_sync()
    yield device
    device.destroy()


@pytest.fixture
def wesl_compiler(
    wesl_options: CompileOptions,
    wesl_modules: Mapping[str, str],
    wesl_filenames: Mapping[str, str | Path],
    wesl_root_directory: Path,
    wesl_dependencies: Mapping[str, str | Path],
) -> Compiler:
    return Compiler(
        options=wesl_options,
        modules=wesl_modules,
        filenames=wesl_filenames,
        root_directory=wesl_root_directory,
        dependencies=wesl_dependencies,
    )


@pytest.fixture
def _wesl_project(request: pytest.FixtureRequest) -> Project | None:
    return load_project(request.node.path.parent)


@pytest.fixture
def wesl_dependencies() -> Mapping[str, str | Path]:
    return {}


@pytest.fixture
def wesl_resources() -> Mapping[int, Sequence[dict[str, Any]]]:
    return {}


@pytest.fixture
def wesl_layouts() -> Mapping[int, Sequence[dict[str, Any]]] | None:
    return None


@pytest.fixture
def wesl_modules() -> Mapping[str, str]:
    return {}


@pytest.fixture
def wesl_filenames() -> Mapping[str, str | Path]:
    return {}


@pytest.fixture
def wesl_features() -> Features:
    return Features()


@pytest.fixture
def wesl_options(
    wesl_features: Features | Mapping[str, bool | Feature],
) -> CompileOptions:
    return CompileOptions(
        features=Features(flags=dict(wesl_features))
        if isinstance(wesl_features, Mapping)
        else wesl_features
    )


@pytest.fixture
def wesl_test_options(
    wesl_features: Features | Mapping[str, bool | Feature],
) -> TestOptions:
    return TestOptions(
        features=Features(flags=dict(wesl_features))
        if isinstance(wesl_features, Mapping)
        else wesl_features
    )


@pytest.fixture
def wesl_constants() -> Mapping[str, float]:
    return {}


@pytest.fixture
def wesl_root_directory(
    request: pytest.FixtureRequest,
    pytestconfig: pytest.Config,
    _wesl_project: Project | None,
) -> Path:
    if directory := pytestconfig.getini("wesl_root"):
        return Path(abspath(pytestconfig.rootpath / directory))
    return (
        request.node.path.parent
        if _wesl_project is None
        else _wesl_project.root_directory
    )
