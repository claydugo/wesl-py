from pathlib import Path

import pytest
import wesl
from wesl.testing import ShaderAssertionError, run_test_cpu


@pytest.mark.parametrize(
    "line_break",
    ["\n", "\r\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"],
    ids=["lf", "crlf", "cr", "vertical-tab", "form-feed", "nel", "line", "paragraph"],
)
def test_failure_report_renders_shader_source(tmp_path: Path, line_break: str) -> None:
    source = line_break.join(
        [
            "fn vérify() {",
            "\twgsl_test::expectEq(",
            "\t\t3u + 4u,",
            "\t\t8u,",
            "\t);",
            "}",
            "@test fn failure() { vérify(); }",
        ]
    )
    filename = tmp_path / "shaders/math.test.wesl"
    with pytest.raises(ShaderAssertionError) as captured:
        run_test_cpu(
            {"package::main": source},
            "failure",
            filenames={"package::main": filename},
            root_directory=tmp_path,
        )
    error = captured.value
    start = source.encode().index(b"wgsl_test")
    assert error.diagnostic.span == (start, source.encode().index(b");") + 2)
    assert error.diagnostic.source == source
    assert error.diagnostic.filename == str(filename)
    assert str(error) == (
        "error: expectEq failed\n"
        f" --> {Path('shaders', 'math.test.wesl')}:2:2\n"
        "  |\n"
        "2 | /     wgsl_test::expectEq(\n"
        "3 | |         3u + 4u,\n"
        "4 | |         8u,\n"
        "5 | |     );\n"
        "  | |______^ expectEq failed\n"
        "  |\n"
        f"  = note: in package::main ({Path('shaders', 'math.test.wesl')})\n\n"
        "  actual:   7u\n"
        "  expected: 8u\n\n"
        "1 of 1 assertions failed"
    )


@pytest.mark.parametrize(
    ("filename", "source", "span", "fragment"),
    [
        (
            None,
            None,
            None,
            (
                "error: expect failed (first failure)\n"
                "  |\n"
                "  = note: in package::main\n\n"
                "  actual:   false\n"
                "  expected: true\n\n"
                "2 of 3 assertions failed"
            ),
        ),
        ("shader.wesl", None, None, "  = note: in package::main (shader.wesl)\n\n"),
        ("shader.wesl", "éx", (1, 2), "expect failed"),
        ("shader.wesl", "éx", (0, 1), "expect failed"),
        ("shader.wesl", "éx", (3, 2), "expect failed"),
        ("shader.wesl", "éx", (0, 99), "expect failed"),
        (
            "shader.wesl",
            "expect(false);\n}",
            (0, 15),
            "2 | | }\n  | |_^ expect failed (first failure)\n",
        ),
    ],
    ids=[
        "without-filename-or-source",
        "without-source",
        "start-inside-utf8",
        "end-inside-utf8",
        "reversed",
        "past-eof",
        "through-newline",
    ],
)
def test_failure_report_tolerates_unusual_diagnostics(
    filename: str | None,
    source: str | None,
    span: tuple[int, int] | None,
    fragment: str,
) -> None:
    error = ShaderAssertionError(
        wesl.Diagnostic(
            "expect",
            module="package::main",
            filename=filename,
            source=source,
            span=span,
        ),
        actual=False,
        expected=True,
        failures=2,
        checks=3,
    )
    report = str(error)
    assert report.startswith("error: expect failed (first failure)\n")
    assert fragment in report
    assert ("-->" in report) is (span == (0, 15))
    assert report.endswith(
        "  actual:   false\n  expected: true\n\n2 of 3 assertions failed"
    )
    assert error.diagnostic.span == span
