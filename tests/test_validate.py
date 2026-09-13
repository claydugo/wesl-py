from pathlib import Path

import pytest
import wesl


def test_validate_accepts_compute_shaders_and_overrides() -> None:
    source = """
        override size: u32 = 1u;
        @group(0) @binding(0) var<storage, read_write> output: array<u32>;
        @compute @workgroup_size(size) fn main() { output[0] = size; }
    """
    assert wesl.validate(source) is None


@pytest.mark.parametrize(
    ("source", "has_span"),
    [
        ("@compute @workgroup_size(1) fn main() { let value: u32 = true; }", True),
        ("@compute @workgroup_size(1) fn main() { discard; }", False),
        ("fn main( }", True),
        ("import package::helper::value; fn main() {}", True),
    ],
)
def test_validate_reports_source_diagnostics(source: str, *, has_span: bool) -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.validate(source, filename=Path("shaders/invalid.wgsl"))
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.source == source
    assert diagnostic.filename == str(Path("shaders/invalid.wgsl"))
    assert diagnostic.message
    assert diagnostic.module is None
    assert (diagnostic.span is not None) is has_span
    assert (diagnostic.line is not None) is has_span
    assert (diagnostic.column is not None) is has_span
    assert str(Path("shaders/invalid.wgsl")) in str(caught.value)
    assert "\x1b[" not in str(caught.value)
