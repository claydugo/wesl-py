from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


def test_check_syntax_only_parses() -> None:
    assert wesl.check_syntax("") is None
    assert (
        wesl.check_syntax("""
        import alpha::missing::value;
        @if(enabled) fn main() {
            value();
            absent();
            let result: u32 = true;
        }
    """)
        is None
    )


@pytest.mark.parametrize(
    "filename",
    [
        "C:\\shaders\\main.wesl",
        "generated café #7",
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
