from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


def test_check_syntax_does_not_resolve_imports_or_validate_types() -> None:
    assert wesl.check_syntax("") is None
    assert (
        wesl.check_syntax("import alpha::missing::value; fn main() { value(); }")
        is None
    )
    assert wesl.check_syntax("@if(enabled) fn main() { absent(); }") is None
    assert wesl.check_syntax("fn main() { let value: u32 = true; }") is None


@pytest.mark.parametrize(
    "filename",
    [
        "shader.wesl",
        "../shaders/edge-case.frag.wgsl",
        "C:\\shaders\\main.wesl",
        "generated shader #7",
        "shaders/café.wesl",
        "package::::main",
        "",
    ],
)
def test_filename_labels_syntax_errors(filename: str) -> None:
    assert wesl.check_syntax("fn café() {}", filename=filename) is None
    source = "fn café() { ) }"
    with pytest.raises(wesl.CompileError) as caught:
        wesl.check_syntax(source, filename=filename)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.filename == filename
    assert diagnostic.module is None
    assert diagnostic.source == source
    start = source.encode().rindex(b")")
    assert diagnostic.span == (start, start + 1)
    assert filename in str(caught.value)
    assert "fn café()" in str(caught.value)
    with pytest.raises(AttributeError):
        diagnostic.filename = "changed.wesl"


def test_default_filename_identifies_string_source() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.check_syntax("fn main(")
    assert caught.value.diagnostics[0].filename == "<string>"
    assert "<string>" in str(caught.value)


def test_filenames_accept_paths_without_reading_them(tmp_path: Path) -> None:
    filename = tmp_path / "missing.wesl"
    assert wesl.check_syntax("fn main() {}", filename=filename) is None
    with pytest.raises(wesl.CompileError) as caught:
        wesl.check_syntax("fn main(", filename=filename)
    assert caught.value.diagnostics[0].filename == str(filename)
    assert str(filename) in str(caught.value)
    assert not filename.exists()


@pytest.mark.parametrize("source", [None, 1, b"fn main() {}", []])
def test_check_syntax_rejects_invalid_source_types(source: object) -> None:
    with pytest.raises(TypeError):
        wesl.check_syntax(source)


@pytest.mark.parametrize("filename", [None, 1, b"main.wesl"])
def test_check_syntax_rejects_invalid_filename_types(filename: object) -> None:
    with pytest.raises(TypeError):
        wesl.check_syntax("", filename=filename)
