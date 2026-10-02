from pathlib import Path

import pytest
import wesl
from wesl.testing import ShaderAssertionError


@pytest.mark.parametrize(
    ("include_newline", "ending"),
    [
        (False, "  | |______^ expectEq failed\n"),
        (True, "6 | | }\n  | |_^ expectEq failed\n"),
    ],
    ids=["through-semicolon", "through-newline"],
)
def test_failure_source_span(
    tmp_path: Path, ending: str, *, include_newline: bool
) -> None:
    source = (
        "fn vérify() {\r\n\twgsl_test::expectEq(\r\n"
        "\t\t3u + 4u,\r\n\t\t8u,\r\n\t);\r\n}"
    )
    start = source.encode().index(b"wgsl_test")
    end = source.encode().index(b");") + (4 if include_newline else 2)
    filename = tmp_path / "shaders" / "math.test.wesl"
    error = ShaderAssertionError(
        wesl.Diagnostic(
            "expectEq", filename=str(filename), source=source, span=(start, end)
        ),
        actual=7,
        expected=8,
        failures=1,
        checks=1,
        root_directory=tmp_path,
    )
    assert str(error) == (
        "error: expectEq failed\n"
        f" --> {filename.relative_to(tmp_path)}:2:2\n"
        "  |\n"
        "2 | /     wgsl_test::expectEq(\n"
        "3 | |         3u + 4u,\n"
        "4 | |         8u,\n"
        "5 | |     );\n"
        f"{ending}"
        "  |\n"
        f"  = note: in {filename.relative_to(tmp_path)}\n\n"
        "  actual:   7u\n"
        "  expected: 8u\n\n"
        "1 of 1 assertions failed"
    )
    assert error.diagnostic.filename == str(filename)


def test_failure_without_source() -> None:
    error = ShaderAssertionError(
        wesl.Diagnostic("expect", module="package::main"),
        actual=False,
        expected=True,
        failures=2,
        checks=3,
    )
    assert str(error) == (
        "error: expect failed (first failure)\n"
        "  |\n"
        "  = note: in package::main\n\n"
        "  actual:   false\n"
        "  expected: true\n\n"
        "2 of 3 assertions failed"
    )


@pytest.mark.parametrize(
    "span",
    [(1, 2), (0, 1), (3, 2), (0, 99)],
    ids=["start-inside-utf8", "end-inside-utf8", "reversed", "past-eof"],
)
def test_failure_with_invalid_source_span(span: tuple[int, int]) -> None:
    error = ShaderAssertionError(
        wesl.Diagnostic("expect", source="éx", span=span),
        actual=False,
        expected=True,
        failures=1,
        checks=1,
    )
    assert "expect failed" in str(error)
    assert "-->" not in str(error)
    assert error.diagnostic.span == span


@pytest.mark.parametrize(
    "line_break",
    ["\n", "\r\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"],
    ids=["lf", "crlf", "cr", "vertical-tab", "form-feed", "nel", "line", "paragraph"],
)
def test_failure_with_unicode_line_breaks(line_break: str) -> None:
    source = f"fn café() {{{line_break}    wgsl_test::expect(false);{line_break}}}"
    start = source.encode().index(b"wgsl_test")
    end = source.encode().index(b";") + 1
    error = ShaderAssertionError(
        wesl.Diagnostic(
            "expect", filename="shader.wesl", source=source, span=(start, end)
        ),
        actual=False,
        expected=True,
        failures=1,
        checks=1,
    )
    assert (error.diagnostic.line, error.diagnostic.column) == (2, 5)
    assert "--> shader.wesl:2:5" in str(error)
    assert "2 |     wgsl_test::expect(false);\n" in str(error)
    assert error.diagnostic.source == source
    assert error.diagnostic.span == (start, end)
