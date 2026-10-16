import pickle
import re
from concurrent.futures import ThreadPoolExecutor

import pytest
import wesl
from wesl import _native


@pytest.mark.parametrize(
    ("source", "message", "span"),
    [
        pytest.param(
            "fn café() { let value = 1 💥 + 2; }",
            "invalid token",
            (27, 31),
            id="unexpected-character",
        ),
        pytest.param(
            "fn café() {}\n/* outer /* inner */",
            "invalid token",
            (14, 34),
            id="unterminated-comment",
        ),
        pytest.param(
            "enable f16;\nconst café = 1u;\n"
            "@if(enabled) import package::helper::value;",
            "imports must precede directives and declarations",
            (43, 49),
            id="misplaced-import",
        ),
        pytest.param(
            "import package::{import};",
            "unexpected token `import`, expected .*",
            (17, 23),
            id="malformed-import",
        ),
    ],
)
def test_parse_errors_preserve_source_and_byte_spans(
    source: str, message: str, span: tuple[int, int]
) -> None:
    for operation in (wesl.compile_source, _native.ParsedTestModule):
        with pytest.raises(wesl.CompileError) as caught:
            operation(source, filename="generated.wesl")
        (diagnostic,) = caught.value.diagnostics
        assert re.fullmatch(message, diagnostic.message)
        assert diagnostic.filename == "generated.wesl"
        assert diagnostic.source == source
        assert diagnostic.span == span
        if not message.startswith("imports must precede"):
            assert "imports must precede" not in str(caught.value)


@pytest.mark.parametrize(
    ("replacement", "token", "location", "unmapped_source"),
    [
        pytest.param(
            ("package::settings", "fn value() -> u32 { let café = 1u; return ; ) }"),
            ")",
            "chars 45..46",
            True,
            id="imported-syntax-error",
        ),
        pytest.param(
            (
                "package::settings",
                "fn value() -> u32 { let café = 1u; return absent; }",
            ),
            "absent",
            "in declaration of `value` in package::settings",
            False,
            id="undefined-symbol",
        ),
        pytest.param(
            ("package::main", "fn café(  \u2028"),
            "",
            "chars 14..14",
            True,
            id="root-end-of-file",
        ),
        pytest.param(
            ("package::settings", "fn café(  \u2028"),
            "",
            "chars 14..14",
            True,
            id="imported-end-of-file",
        ),
    ],
)
def test_compile_errors_own_module_diagnostics(
    modules: dict[str, str],
    replacement: tuple[str, str],
    token: str,
    location: str,
    *,
    unmapped_source: bool,
) -> None:
    module, source = replacement
    modules[module] = source
    encoded = source.encode()
    start = encoded.rindex(token.encode()) if token else len(encoded)
    span = (start, start + len(token.encode()))
    expected = []
    for sourcemap in (False, True):
        with pytest.raises(wesl.CompileError) as caught:
            wesl.compile(
                modules, options=wesl.CompileOptions(sourcemap=sourcemap, strip=False)
            )
        error = caught.value
        (diagnostic,) = error.diagnostics
        retained = source if sourcemap or unmapped_source else None
        assert diagnostic.module == module
        assert diagnostic.filename is None
        assert diagnostic.source == retained
        assert diagnostic.span == span
        assert diagnostic.message
        assert location in str(error)
        assert module in str(error)
        assert "invalid source location" not in str(error)
        assert "\x1b[" not in str(error)
        expected.append((diagnostic, retained))
    for _ in range(32):
        with pytest.raises(wesl.CompileError):
            wesl.compile_source("fn other(")
    modules.clear()
    for diagnostic, retained in expected:
        assert diagnostic.source == retained
        assert diagnostic.span == span


def test_compile_errors_survive_pickling_and_threads() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile({})
    missing = caught.value.diagnostics[0]
    assert (missing.module, missing.source, missing.span) == (None, None, None)

    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile({"package::main": "fn café("})
    error = caught.value
    error.add_note("worker failure")
    restored = pickle.loads(pickle.dumps(error))
    assert type(restored) is wesl.CompileError
    assert restored.args == error.args
    assert restored.diagnostics == error.diagnostics
    assert restored.__notes__ == error.__notes__

    def syntax_failure(index: int) -> wesl.Diagnostic:
        with pytest.raises(wesl.CompileError) as caught:
            wesl.compile_source(
                f"fn function_{index}(", filename=f"shader_{index}.wesl"
            )
        return caught.value.diagnostics[0]

    with ThreadPoolExecutor(max_workers=8) as executor:
        diagnostics = list(executor.map(syntax_failure, range(64)))
    for index, diagnostic in enumerate(diagnostics):
        assert diagnostic.module == "package::main"
        assert diagnostic.filename == f"shader_{index}.wesl"
        assert diagnostic.source == f"fn function_{index}("


def test_diagnostics_are_values_with_unicode_positions() -> None:
    diagnostic = wesl.Diagnostic("invalid token", filename="shader.wesl", span=(0, 1))
    duplicate = wesl.Diagnostic("invalid token", filename="shader.wesl", span=(0, 1))
    assert diagnostic == duplicate
    assert len({diagnostic, duplicate}) == 1
    assert diagnostic != wesl.Diagnostic("invalid token", filename="other.wesl")
    assert diagnostic.module is None
    assert diagnostic.source is None
    assert pickle.loads(pickle.dumps(diagnostic)) == diagnostic
    with pytest.raises(AttributeError):
        diagnostic.message = "changed"

    for line_break in ["\n", "\r\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"]:
        source = f"fn café() {{{line_break}    let café = café;{line_break}}}"
        start = source.encode().rindex("café".encode())
        positioned = wesl.Diagnostic(
            "failed", source=source, span=(start, start + len("café".encode()))
        )
        position = (
            positioned.line,
            positioned.column,
            positioned.end_line,
            positioned.end_column,
        )
        assert (line_break, position) == (line_break, (2, 16, 2, 20))

    for source, span, expected in [
        ("café?", (5, 6), (1, 5, 1, 6)),
        (None, (0, 1), (None, None, None, None)),
        ("café", None, (None, None, None, None)),
        ("café", (4, 99), (None, None, None, None)),
    ]:
        positioned = wesl.Diagnostic("failed", source=source, span=span)
        position = (
            positioned.line,
            positioned.column,
            positioned.end_line,
            positioned.end_column,
        )
        assert (source, span, position) == (source, span, expected)
