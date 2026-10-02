import pickle
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
import wesl
from wesl import _native


@pytest.mark.parametrize(
    "operation", [wesl.check_syntax, wesl.compile_source, _native.discover_tests]
)
def test_misplaced_import_explains_ordering(
    operation: Callable[..., object],
) -> None:
    source = (
        "enable f16;\nconst café = 1u;\n@if(enabled) import package::helper::value;"
    )
    with pytest.raises(
        wesl.CompileError, match="imports must precede directives and declarations"
    ) as caught:
        operation(source, filename="generated.wesl")
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.message == "imports must precede directives and declarations"
    assert diagnostic.filename == "generated.wesl"
    assert diagnostic.source == source
    start = source.encode().index(b"import")
    assert diagnostic.span == (start, start + len(b"import"))


def test_malformed_import_keeps_parser_diagnostic() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.check_syntax("import package::{import};")
    assert "unexpected token" in caught.value.diagnostics[0].message
    assert "imports must precede" not in str(caught.value)


def test_imported_syntax_error_has_owned_diagnostics(modules: dict[str, str]) -> None:
    source = "fn value() -> u32 { let café = 1u; return ; ) }"
    modules["package::settings"] = source
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile(modules)
    error = caught.value
    (diagnostic,) = error.diagnostics
    assert diagnostic.module == "package::settings"
    assert diagnostic.filename is None
    assert diagnostic.source == source
    start = source.encode().index(b") }")
    assert diagnostic.span == (start, start + 1)
    assert diagnostic.message
    assert "settings" in str(error)
    assert "\x1b[" not in str(error)
    for _ in range(32):
        with pytest.raises(wesl.CompileError):
            wesl.check_syntax("fn other(")
    modules.clear()
    assert diagnostic.source == source
    assert diagnostic.span == (start, start + 1)


@pytest.mark.parametrize(
    "sourcemap", [False, True], ids=["no-source-map", "source-map"]
)
def test_imported_undefined_symbol_has_byte_span(
    modules: dict[str, str], *, sourcemap: bool
) -> None:
    source = "fn value() -> u32 { let café = 1u; return absent; }"
    modules["package::settings"] = source
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile(modules, options=wesl.CompileOptions(sourcemap=sourcemap))
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.module == "package::settings"
    assert diagnostic.filename is None
    assert diagnostic.source == (source if sourcemap else None)
    start = source.encode().index(b"absent")
    assert diagnostic.span == (start, start + len(b"absent"))


def test_missing_root_does_not_fabricate_metadata() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile({})
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.module is None
    assert diagnostic.source is None
    assert diagnostic.span is None


@pytest.mark.parametrize("module", ["package::main", "package::helper"])
def test_compiler_eof_spans_are_zero_width(module: str) -> None:
    source = "fn café(  \u2028"
    modules = {"package::main": "import package::helper::main; fn entry() { main(); }"}
    modules[module] = source
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile(modules, options=wesl.CompileOptions(strip=False))
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.module == module
    assert diagnostic.source == source
    assert diagnostic.span == (len(source.encode()), len(source.encode()))
    assert "invalid source location" not in str(caught.value)
    assert f"chars {len(source.encode())}..{len(source.encode())}" in str(caught.value)


def test_concurrent_diagnostics_remain_independent() -> None:
    def syntax_failure(index: int) -> wesl.Diagnostic:
        source = f"fn function_{index}("
        with pytest.raises(wesl.CompileError) as caught:
            wesl.check_syntax(source, filename=f"shader_{index}.wesl")
        return caught.value.diagnostics[0]

    with ThreadPoolExecutor(max_workers=8) as executor:
        diagnostics = list(executor.map(syntax_failure, range(64)))
    for index, diagnostic in enumerate(diagnostics):
        assert diagnostic.module is None
        assert diagnostic.filename == f"shader_{index}.wesl"
        assert diagnostic.source == f"fn function_{index}("


def test_diagnostics_are_immutable_values() -> None:
    diagnostic = wesl.Diagnostic("invalid token", filename="shader.wesl", span=(0, 1))
    assert diagnostic == wesl.Diagnostic(
        "invalid token", filename="shader.wesl", span=(0, 1)
    )
    assert diagnostic != wesl.Diagnostic("invalid token", filename="other.wesl")
    assert (
        len(
            {
                diagnostic,
                wesl.Diagnostic("invalid token", filename="shader.wesl", span=(0, 1)),
            }
        )
        == 1
    )
    assert diagnostic.module is None
    assert diagnostic.source is None
    assert pickle.loads(pickle.dumps(diagnostic)) == diagnostic
    with pytest.raises(AttributeError):
        diagnostic.message = "changed"


@pytest.mark.parametrize(
    "line_break",
    ["\n", "\r\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"],
    ids=["lf", "crlf", "cr", "vertical-tab", "form-feed", "nel", "line", "paragraph"],
)
def test_diagnostic_positions_use_unicode_columns(line_break: str) -> None:
    source = f"fn café() {{{line_break}    let café = café;{line_break}}}"
    start = source.encode().rindex(b"caf\xc3\xa9")
    diagnostic = wesl.Diagnostic(
        "failed", source=source, span=(start, start + len("café".encode()))
    )
    assert (diagnostic.line, diagnostic.column) == (2, 16)
    assert (diagnostic.end_line, diagnostic.end_column) == (2, 20)


@pytest.mark.parametrize(
    ("source", "span", "position"),
    [
        pytest.param("café?", (5, 6), (1, 5, 1, 6), id="utf8-byte-offset"),
        pytest.param(None, (0, 1), (None, None, None, None), id="missing-source"),
        pytest.param("café", None, (None, None, None, None), id="missing-span"),
        pytest.param("café", (4, 99), (None, None, None, None), id="invalid-span"),
    ],
)
def test_diagnostic_positions_require_source_and_valid_byte_spans(
    source: str | None,
    span: tuple[int, int] | None,
    position: tuple[int | None, ...],
) -> None:
    diagnostic = wesl.Diagnostic("failed", source=source, span=span)
    assert (
        diagnostic.line,
        diagnostic.column,
        diagnostic.end_line,
        diagnostic.end_column,
    ) == position


def test_compile_errors_preserve_diagnostics_through_pickle() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile({"package::main": "fn café("})
    error = caught.value
    error.add_note("worker failure")
    restored = pickle.loads(pickle.dumps(error))
    assert type(restored) is wesl.CompileError
    assert restored.args == error.args
    assert restored.diagnostics == error.diagnostics
    assert restored.__notes__ == error.__notes__
