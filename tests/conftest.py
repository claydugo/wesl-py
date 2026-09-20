import pytest

pytest_plugins = ["pytester"]


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
