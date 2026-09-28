import os
import pickle
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from importlib.metadata import version
from multiprocessing import get_context
from pathlib import Path

import pytest
import wesl
from wesl import _native


@pytest.mark.parametrize(
    "source",
    [
        "const café = 1u;\nimport package::helper::value;",
        "enable f16;\n@if(enabled) import package::helper::value;",
    ],
)
@pytest.mark.parametrize(
    "operation", [wesl.check_syntax, wesl.compile_source, _native.discover_tests]
)
def test_misplaced_import_explains_ordering(
    source: str, operation: Callable[..., object]
) -> None:
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


@pytest.mark.parametrize("strip", [False, True])
@pytest.mark.parametrize("lower", [False, True])
def test_shader_test_options_control_translation(
    wgsl_test: Path, *, strip: bool, lower: bool
) -> None:
    compiled = _native.compile_test(
        {
            "package::main": (
                "alias Number = u32; const amount = 3u; "
                "fn unused() {} "
                "@test fn selected() { "
                "let value: Number = amount; wgsl_test::expectEq(value, 3u); }"
            ),
        },
        "package::main",
        "selected",
        wesl.TestOptions(strip=strip, lower=lower),
        {},
        None,
        0,
        {"wgsl_test": str(wgsl_test)},
    )
    assert compiled is not None
    shader, entry_point, diagnostics, _, _ = compiled
    assert ("unused" in shader) is not strip
    assert ("alias " in shader) is not lower
    assert entry_point in shader
    assert len(diagnostics) == 1


def test_shader_test_options_control_validation(wgsl_test: Path) -> None:
    modules = {
        "package::main": "fn same() {} fn same() {} @test fn selected() {}",
    }
    with pytest.raises(wesl.CompileError, match="duplicate declaration"):
        _native.compile_test(
            modules,
            "package::main",
            "selected",
            wesl.TestOptions(strip=False),
            {},
            None,
            0,
            {"wgsl_test": str(wgsl_test)},
        )
    compiled = _native.compile_test(
        modules,
        "package::main",
        "selected",
        wesl.TestOptions(strip=False, validate=False),
        {},
        None,
        0,
        {"wgsl_test": str(wgsl_test)},
    )
    assert compiled is not None
    assert compiled[0].count("same(") == 2  # noqa: PLR2004


@pytest.mark.parametrize(
    "module", ["package::main", "package::helper", "wgsl_test::TestResult"]
)
def test_shader_test_error_preserves_source_context(
    module: str, wgsl_test: Path
) -> None:
    source = "fn fail() {\n    let café = 1u;\n    let item = missing;\n}\n"
    modules = {
        "package::main": "@test fn selected() { package::helper::fail(); }",
    }
    if module == "package::main":
        source += "@test fn selected() { fail(); }"
    elif module == "wgsl_test::TestResult":
        modules["package::main"] = "@test fn selected() {}"
        source += (
            (wgsl_test / "TestResult.wesl")
            .read_text(encoding="utf-8")
            .replace("fn initTestResult() {", "fn initTestResult() { fail();")
        )
    modules[module] = source
    with pytest.raises(wesl.CompileError) as caught:
        _native.compile_test(
            modules,
            "package::main",
            "selected",
            wesl.TestOptions(),
            {module: "shader.wesl"},
            None,
            0,
            {"wgsl_test": str(wgsl_test)},
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


@pytest.mark.parametrize("strip", [False, True])
def test_disabled_shader_skips_missing_imports(*, strip: bool) -> None:
    result = _native.compile_test(
        {
            "package::main": (
                "import package::missing::value; "
                "@if(enabled) @test fn selected() {} "
                "fn unrelated() { value(); }"
            ),
        },
        "package::main",
        "selected",
        wesl.TestOptions(strip=strip, features=wesl.Features(flags={"enabled": False})),
        {},
        None,
        0,
        {},
    )
    assert result is None


@pytest.mark.parametrize("registration", ["directory", "modules"])
def test_shader_tests_reject_scoped_assertion_overrides(
    tmp_path: Path, wgsl_test: Path, registration: str
) -> None:
    modules = {
        "package::main": "@test fn selected() { library::verify(); }",
        "library": "import wgsl_test::customCheck; fn verify() { customCheck(); }",
    }
    dependencies = {"wgsl_test": str(wgsl_test)}
    if registration == "directory":
        (tmp_path / "package.wesl").write_text("fn customCheck() {}")
        dependencies["library/wgsl_test"] = str(tmp_path)
    else:
        modules["library/wgsl_test"] = "fn customCheck() {}"
    result = wesl.compile(
        modules,
        options=wesl.CompileOptions(keep=["selected"]),
        dependencies=dependencies,
    )
    assert "library/wgsl_test" in result.modules
    with pytest.raises(
        wesl.CompileError,
        match="shader tests do not support scoped wgsl_test overrides",
    ):
        _native.compile_test(
            modules,
            "package::main",
            "selected",
            wesl.TestOptions(),
            {},
            None,
            0,
            dependencies,
        )


@pytest.mark.parametrize(("parameters", "arguments"), [("", ""), ("value: u32", "1u")])
def test_shader_tests_reject_assertions_with_missing_parameters(
    wgsl_test: Path, parameters: str, arguments: str
) -> None:
    source = f"fn expectCustom({parameters}) {{}}"
    with pytest.raises(wesl.CompileError, match="shader assertions require") as caught:
        _native.compile_test(
            {
                "package::main": (
                    f"@test fn selected() {{ wgsl_test::expectCustom({arguments}); }}"
                ),
                "wgsl_test": source,
            },
            "package::main",
            "selected",
            wesl.TestOptions(),
            {"wgsl_test": "assertions.wesl"},
            None,
            0,
            {"wgsl_test": str(wgsl_test)},
        )
    [diagnostic] = caught.value.diagnostics
    assert diagnostic.module == "wgsl_test"
    assert diagnostic.filename == "assertions.wesl"
    assert diagnostic.source == source
    assert diagnostic.span == (0, len(source.encode()))


@pytest.mark.parametrize("value_type", ["i32", "vec2<u32>"])
def test_shader_assertion_types_preserve_source_context(
    wgsl_test: Path, value_type: str
) -> None:
    source = (
        f"alias Value = {value_type}; "
        "fn expectCustom(actual: Value, expected: Value) {}"
    )
    with pytest.raises(wesl.CompileError, match="shader assertion values") as caught:
        _native.compile_test(
            {
                "package::main": (
                    "@test fn selected() { wgsl_test::expectCustom(1, 2); }"
                ),
                "wgsl_test": source,
            },
            "package::main",
            "selected",
            wesl.TestOptions(),
            {"wgsl_test": "assertions.wesl"},
            None,
            0,
            {"wgsl_test": str(wgsl_test)},
        )
    [diagnostic] = caught.value.diagnostics
    assert diagnostic.module == "wgsl_test"
    assert diagnostic.filename == "assertions.wesl"
    assert diagnostic.source == source
    assert diagnostic.span == (source.index("fn expectCustom"), len(source))


@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize(
    "declarations",
    [
        "alias Value = Value;",
        "alias Value = Other; alias Other = Value;",
        "alias Value = array<Value, 2>;",
        "struct Value { child: Value }",
    ],
)
def test_shader_assertion_type_cycles_without_validation(
    pytester: pytest.Pytester, wgsl_test: Path, declarations: str, *, lower: bool
) -> None:
    source = f"{declarations} fn expectCustom(actual: Value, expected: Value) {{}}"
    completed = pytester.run(
        sys.executable,
        "-c",
        (
            "import wesl\n"
            "from wesl import _native\n"
            "try:\n"
            "    _native.compile_test(\n"
            "        {'package::main': '@test fn selected() { "
            "wgsl_test::expectCustom(1, 2); }',\n"
            f"         'wgsl_test': {source!r}}},\n"
            "        'package::main', 'selected',\n"
            f"        wesl.TestOptions(validate=False, lower={lower!r}),\n"
            "        {'wgsl_test': 'assertions.wesl'}, None, 0,\n"
            f"        {{'wgsl_test': {str(wgsl_test)!r}}},\n"
            "    )\n"
            "except wesl.CompileError as error:\n"
            "    [diagnostic] = error.diagnostics\n"
            "    assert 'cyclic' in diagnostic.message\n"
            "    assert diagnostic.module == 'wgsl_test'\n"
            "    assert diagnostic.filename == 'assertions.wesl'\n"
            f"    assert diagnostic.source == {source!r}\n"
            "else:\n"
            "    raise AssertionError('cyclic assertion type compiles')\n"
        ),
        timeout=10,
    )
    assert completed.ret == 0, completed.stdout.str() + completed.stderr.str()


@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize(
    "member",
    ["@align(0) extra: u32,", "extra: Nested,", "extra: array<Nested, 2>,"],
)
def test_shader_result_rejects_zero_alignment(
    wgsl_test: Path, member: str, *, lower: bool
) -> None:
    source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    source = "struct Nested { @align(0) value: u32 }\n" + source.replace(
        "struct TestResult {", f"struct TestResult {{ {member}"
    )
    with pytest.raises(wesl.CompileError, match="nonzero alignment") as caught:
        _native.compile_test(
            {
                "package::main": "@test fn selected() { wgsl_test::expect(true); }",
                "wgsl_test::TestResult": source,
            },
            "package::main",
            "selected",
            wesl.TestOptions(lower=lower),
            {"wgsl_test::TestResult": "results.wesl"},
            None,
            0,
            {"wgsl_test": str(wgsl_test)},
        )
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.module == "wgsl_test::TestResult"
    assert diagnostic.filename == "results.wesl"
    assert diagnostic.source == source


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
