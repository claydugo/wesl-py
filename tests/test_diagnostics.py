import os
import pickle
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from importlib.metadata import version
from multiprocessing import get_context

import pytest
import wesl
from wesl import _native


def test_imported_syntax_error_has_owned_diagnostics(modules: dict[str, str]) -> None:
    source = "fn value() -> u32 { let café = 1u; return ; ) }"
    modules["package::settings"] = source
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile(modules)
    error = caught.value
    assert isinstance(error, Exception)
    assert isinstance(error.diagnostics, tuple)
    assert len(error.diagnostics) == 1
    diagnostic = error.diagnostics[0]
    assert isinstance(diagnostic, wesl.Diagnostic)
    assert diagnostic.module == "package::settings"
    assert diagnostic.filename is None
    assert diagnostic.source == source
    start = source.encode().index(b") }")
    assert diagnostic.span == (start, start + 1)
    assert diagnostic.message
    assert "settings" in str(error)
    assert "\x1b[" not in str(error)
    for attribute, value in [("message", "changed"), ("span", (0, 1))]:
        with pytest.raises(AttributeError):
            setattr(diagnostic, attribute, value)
    for _ in range(32):
        with pytest.raises(wesl.CompileError):
            wesl.check_syntax("fn other(")
    modules.clear()
    assert diagnostic.source == source
    assert diagnostic.span == (start, start + 1)


@pytest.mark.parametrize("sourcemap", [False, True])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="WESL 0.5.0 omits module context from validation errors",
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
    assert diagnostic.source == source
    start = source.encode().index(b"absent")
    assert diagnostic.span == (start, start + len(b"absent"))


@pytest.mark.parametrize("module", ["package::main", "package::helper"])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="WESL 0.5.0 omits module context from validation errors",
)
def test_shader_test_error_preserves_source_context(module: str) -> None:
    source = "fn fail() {\n    let café = 1u;\n    let item = missing;\n}\n"
    modules = {
        "package::main": "@test fn selected() { package::helper::fail(); }",
    }
    if module == "package::main":
        source += "@test fn selected() { fail(); }"
    modules[module] = source
    with pytest.raises(wesl.CompileError) as caught:
        _native.compile_test(
            modules,
            "package::main",
            "selected",
            wesl.CompileOptions(),
            {module: "shader.wesl"},
            None,
            0,
        )
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.module == module
    assert diagnostic.filename == "shader.wesl"
    assert diagnostic.source == source
    start = source.encode().index(b"missing")
    assert diagnostic.span == (start, start + len(b"missing"))
    assert (diagnostic.line, diagnostic.column) == (3, 16)
    assert "shader.wesl:3:16" in str(caught.value)
    assert "let item = missing;" in str(caught.value)


def test_linked_argument_error_preserves_missing_metadata() -> None:
    source = "import package::helper::consume; fn main() -> u32 { return consume(); }"
    with pytest.raises(wesl.CompileError, match="number of arguments") as caught:
        wesl.compile(
            {
                "package::main": source,
                "package::helper": "fn consume(value: u32) -> u32 { return value; }",
            },
            options=wesl.CompileOptions(strip=False),
        )
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.module is None
    assert diagnostic.source == source
    start = source.encode().rindex(b"consume()")
    assert diagnostic.span == (start, start + len(b"consume()"))


def test_missing_root_does_not_fabricate_metadata() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile({})
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.module is None
    assert diagnostic.source is None
    assert diagnostic.span is None


@pytest.mark.parametrize("source", ["fn main(", "fn café(", "fn café(  \n"])
def test_syntax_eof_spans_are_zero_width(source: str) -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.check_syntax(source, filename="shaders/café.wesl")
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.module is None
    assert diagnostic.filename == "shaders/café.wesl"
    assert "shaders/café.wesl" in str(caught.value)
    assert "invalid source location" not in str(caught.value)
    assert diagnostic.source == source
    assert diagnostic.span == (len(source.encode()), len(source.encode()))


@pytest.mark.parametrize("source", ["fn main(", "fn café(", "fn café(  \n"])
@pytest.mark.parametrize("module", ["package::main", "package::helper"])
def test_compiler_eof_spans_are_zero_width(source: str, module: str) -> None:
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


def test_version() -> None:
    assert wesl.__version__ == version("wesl-py")


def test_import_does_not_load_gpu_packages() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, wesl; assert 'wgpu' not in sys.modules; "
                "assert 'pygfx' not in sys.modules"
            ),
        ],
        check=True,
    )


def test_compile_errors_ignore_forced_terminal_color() -> None:
    environment = dict(os.environ, CLICOLOR_FORCE="1")
    environment.pop("NO_COLOR", None)
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import wesl\n"
                "try:\n"
                "    wesl.compile({'package::main': 'fn main('})\n"
                "except wesl.CompileError as error:\n"
                "    assert '\\x1b[' not in str(error)\n"
                "    assert 'invalid source location' not in str(error)\n"
                "else:\n"
                "    raise AssertionError('expected a compile error')\n"
            ),
        ],
        env=environment,
        check=True,
    )


def test_manually_constructed_compile_errors_have_no_diagnostics() -> None:
    error = wesl.CompileError("failed")
    assert error.diagnostics == ()
    assert str(error) == "failed"


def test_diagnostic_representation_identifies_the_error() -> None:
    diagnostic = wesl.Diagnostic(
        "invalid token",
        filename="shader.wesl",
        source="fn main() { $ }",
        span=(12, 13),
    )
    assert repr(diagnostic) == (
        "Diagnostic(message='invalid token', module=None, "
        "filename='shader.wesl', span=(12, 13))"
    )
    assert diagnostic.source not in repr(diagnostic)


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
    with pytest.raises(AttributeError):
        diagnostic.message = "changed"
    assert pickle.loads(pickle.dumps(diagnostic)) == diagnostic  # noqa: S301


@pytest.mark.parametrize(
    "line_break", ["\n", "\r\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"]
)
def test_diagnostic_positions_use_unicode_columns(line_break: str) -> None:
    source = f"fn café() {{{line_break}    let café = 1u;{line_break}}}"
    start = source.encode().rindex(b"caf\xc3\xa9")
    diagnostic = wesl.Diagnostic(
        "failed", source=source, span=(start, len(source.encode()))
    )
    assert (diagnostic.line, diagnostic.column) == (2, 9)
    assert (diagnostic.end_line, diagnostic.end_column) == (3, 2)
    diagnostic = wesl.Diagnostic("failed", source="café?", span=(5, 6))
    assert (diagnostic.line, diagnostic.column) == (1, 5)
    assert (diagnostic.end_line, diagnostic.end_column) == (1, 6)
    assert wesl.Diagnostic("failed", span=(0, 1)).line is None
    assert wesl.Diagnostic("failed", source="café", span=(4, 99)).column is None
    assert wesl.Diagnostic("failed", source="café", span=(4, 99)).end_column is None


def test_compile_errors_preserve_diagnostics_through_pickle() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile({"package::main": "fn café("})
    error = caught.value
    error.add_note("worker failure")
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301
    assert type(restored) is wesl.CompileError
    assert restored.args == error.args
    assert restored.diagnostics == error.diagnostics
    assert restored.__notes__ == error.__notes__


def test_syntax_errors_cross_process_boundaries() -> None:
    with pytest.raises(wesl.CompileError) as expected:
        wesl.check_syntax("fn main(", filename="worker.wesl")
    with ProcessPoolExecutor(
        max_workers=1, mp_context=get_context("spawn")
    ) as executor:
        future = executor.submit(wesl.check_syntax, "fn main(", filename="worker.wesl")
        with pytest.raises(wesl.CompileError) as caught:
            future.result(timeout=10)
    assert caught.value.diagnostics == expected.value.diagnostics
