from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path

import pytest
import wesl

pytest_plugins = ["pytester"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if find_spec("wgpu") is None:
        for item in items:
            if "gpu" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="wgpu is not installed"))


@pytest.fixture(scope="session")
def wgsl_test() -> Path:
    return Path(wesl.__file__).parent / "shaders/wgsl_test"


@pytest.fixture
def wesl_options(wesl_options: wesl.CompileOptions) -> wesl.CompileOptions:
    return replace(wesl_options, visibility=True)


@pytest.fixture
def wesl_test_options(wesl_test_options: wesl.TestOptions) -> wesl.TestOptions:
    return replace(wesl_test_options, visibility=True)


@pytest.fixture
def wesl_dependencies() -> dict[str, Path]:
    return {
        "examples": Path(__file__).parents[1] / "examples",
    }


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--image", action="store_true", help="Also verify the full TIFF.")


@pytest.fixture
def modules() -> dict[str, str]:
    return {
        "package::main": """
            import package::settings::value;
            @group(0) @binding(0)
            var<storage, read_write> output: array<u32>;
            @compute @workgroup_size(1)
            fn main() { output[0] = value(); }
        """,
        "package::settings": """
            @if(enabled) fn value() -> u32 { return 7u; }
            @if(!enabled) fn value() -> u32 { return 3u; }
        """,
    }
