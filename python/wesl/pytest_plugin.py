from __future__ import annotations

import re
import sys
from os.path import abspath
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from _pytest._code.code import ExceptionChainRepr, ExceptionRepr, ReprEntryNative

from . import (
    CompileError,
    CompileOptions,
    Compiler,
    Diagnostic,
    Features,
    TestOptions,
    _native,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from typing import Any

    import wgpu
    from _pytest._io import TerminalWriter


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
        default=".",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "wesl: executes a WESL shader test")
    config.addinivalue_line(
        "markers", "gpu: requires a WebGPU adapter (hardware or software)"
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if (
        "wesl" in report.keywords
        and isinstance(report.longrepr, ExceptionChainRepr)
        and report.longrepr.reprtraceback.style == "value"
    ):
        representation = WeslFailureRepr(report.longrepr.chain)
        representation.sections = report.longrepr.sections
        report.longrepr = representation


class WeslFailureRepr(ExceptionChainRepr):
    def toterminal(self, tw: TerminalWriter) -> None:
        writer = tw
        for traceback, _, description in self.chain:
            if traceback.style != "value":
                traceback.toterminal(writer)
            else:
                for entry in traceback.reprentries:
                    if entry.style != "value":
                        entry.toterminal(writer)
                        continue
                    for index, line in enumerate(entry.lines):
                        if line.startswith(("  actual:", "  expected:")):
                            label, value = line.split(":", 1)
                            other = entry.lines[
                                index + 1 if label == "  actual" else index - 1
                            ].split(":", 1)[1]
                            components = re.split(r"([(),]\s*)", value.lstrip())
                            other_components = re.split(r"([(),]\s*)", other.lstrip())
                            writer.write(
                                label + ":" + value[: len(value) - len(value.lstrip())]
                            )
                            for component, other_component in zip(
                                components, other_components, strict=True
                            ):
                                writer.write(
                                    component,
                                    red=label == "  actual"
                                    and component != other_component,
                                    green=label == "  expected"
                                    and component != other_component,
                                )
                            writer.line()
                        else:
                            writer.line(
                                line,
                                red=index == 0
                                or (line.lstrip().startswith("| ") and "^" in line),
                            )
            if description is not None:
                writer.line()
                writer.line(description, yellow=True)
        ExceptionRepr.toterminal(self, writer)


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
            tests = _native.discover_tests(source, str(self.path))
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
                wesl_device: wgpu.GPUDevice,
                wesl_test_options: TestOptions,
                wesl_modules: Mapping[str, str],
                wesl_filenames: Mapping[str, str | Path],
                wesl_root_directory: Path,
                wesl_dependencies: Mapping[str, str | Path],
                wesl_resources: Mapping[int, Sequence[dict[str, Any]]],
                wesl_constants: Mapping[str, float],
                shader_path: Path = self.path,
                shader_source: str = source,
                shader_name: str = name,
            ) -> None:
                __tracebackhide__ = True
                from .testing import ShaderTestDisabledError, run_test

                root_directory = Path(abspath(wesl_root_directory))  # noqa: PTH100
                relative = shader_path.relative_to(root_directory)
                parts = (*relative.parts[:-1], relative.stem.replace(".", "_"))
                root = "package::" + "::".join(parts)
                if root in wesl_modules:
                    raise ValueError(
                        "the test module is already present in wesl_modules"
                    )
                try:
                    run_test(
                        wesl_device,
                        {**wesl_modules, root: shader_source},
                        shader_name,
                        root=root,
                        options=wesl_test_options,
                        filenames={**wesl_filenames, root: shader_path},
                        root_directory=root_directory,
                        dependencies=wesl_dependencies,
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
        error = ShaderAssertionError(
            excinfo.value.diagnostic,
            actual=excinfo.value.actual,
            expected=excinfo.value.expected,
            failures=excinfo.value.failures,
            checks=excinfo.value.checks,
            root_directory=self.item.config.rootpath,
        )
        representation = excinfo.getrepr(
            style="line" if style == "line" else "value",
            tbfilter=False,
            chain=style != "line",
        )
        entry = representation.reprtraceback.reprentries[-1]
        entry.lines = str(error).splitlines()
        if style == "line":
            entry.lines = entry.lines[:1]
        elif notes := getattr(excinfo.value, "__notes__", ()):
            representation.reprtraceback.reprentries = [
                *representation.reprtraceback.reprentries,
                ReprEntryNative([f"{note}\n" for note in notes]),
            ]
        if representation.reprcrash is not None:
            diagnostic = excinfo.value.diagnostic
            representation.reprcrash.path = error.filename
            representation.reprcrash.lineno = diagnostic.line or 1
            representation.reprcrash.message = f"{diagnostic.message} failed"
        return representation


@pytest.fixture(scope="session")
def wesl_device(request: pytest.FixtureRequest) -> Iterator[wgpu.GPUDevice]:
    try:
        import wgpu
    except ModuleNotFoundError:
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
def wesl_dependencies() -> Mapping[str, str | Path]:
    return {}


@pytest.fixture
def wesl_resources() -> Mapping[int, Sequence[dict[str, Any]]]:
    return {}


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
def wesl_options(wesl_features: Features) -> CompileOptions:
    return CompileOptions(features=wesl_features)


@pytest.fixture
def wesl_test_options(wesl_features: Features) -> TestOptions:
    return TestOptions(features=wesl_features)


@pytest.fixture
def wesl_constants() -> Mapping[str, float]:
    return {}


@pytest.fixture
def wesl_root_directory(pytestconfig: pytest.Config) -> Path:
    return Path(abspath(pytestconfig.rootpath / pytestconfig.getini("wesl_root")))  # noqa: PTH100
