import re
import sys
from functools import partial
from pathlib import Path

import pytest
import wesl
from wesl import _native


@pytest.fixture
def compile_shader_test(wgsl_test: Path) -> partial:
    return partial(
        _native.compile_test,
        root="package::main",
        test_name="selected",
        options=wesl.TestOptions(),
        filenames={},
        root_directory=None,
        result_binding=0,
        dependencies={"wgsl_test": str(wgsl_test)},
    )


def test_shader_lowering_is_not_implemented(compile_shader_test: partial) -> None:
    with pytest.raises(NotImplementedError, match="lowering is not supported"):
        compile_shader_test(
            {"package::main": "@test fn selected() {}"},
            options=wesl.TestOptions(lower=True),
        )


def test_cooperative_wrapper_preserves_other_entry_points(
    compile_shader_test: partial,
) -> None:
    compiled = compile_shader_test(
        {
            "package::main": """
                @compute @workgroup_size(8)
                fn unrelated(@builtin(local_invocation_index) lane: u32) {
                    let unused = lane;
                }
                @if(enabled) {
                    @test
                    fn selected(@builtin(local_invocation_index) lane: u32) {
                        wgsl_test::expectEq(lane, 0u);
                    }
                }
            """
        },
        options=wesl.TestOptions(
            strip=False, features=wesl.Features(flags={"enabled": True})
        ),
    )
    assert compiled is not None
    shader, entry_point, _, _, _ = compiled
    wesl.check_syntax(shader)
    assert re.search(
        r"@compute\s+@workgroup_size\(8\)\s+fn package_main_unrelated\("
        r"@builtin\(local_invocation_index\) lane: u32\)",
        shader,
    )
    assert f"fn {entry_point}(" in shader


def test_shader_test_error_preserves_source_context(
    compile_shader_test: partial, wgsl_test: Path
) -> None:
    source = "fn fail() {\n    let café = 1u;\n    let item = missing;\n}\n"
    source += (
        (wgsl_test / "TestResult.wesl")
        .read_text(encoding="utf-8")
        .replace("fn initTestResult() {", "fn initTestResult() { fail();")
    )
    with pytest.raises(wesl.CompileError) as caught:
        compile_shader_test(
            {
                "package::main": "@test fn selected() {}",
                "wgsl_test::TestResult": source,
            },
            filenames={"wgsl_test::TestResult": "shader.wesl"},
        )
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.module == "wgsl_test::TestResult"
    assert diagnostic.filename == "shader.wesl"
    assert diagnostic.source == source
    start = source.encode().index(b"missing")
    assert diagnostic.span == (start, start + len(b"missing"))
    assert (diagnostic.line, diagnostic.column) == (3, 16)
    assert "shader.wesl:3:16" in str(caught.value)
    assert "let item = missing;" in str(caught.value)


@pytest.mark.parametrize("strip", [False, True], ids=["keep-all", "strip-unused"])
def test_disabled_shader_skips_missing_imports(
    compile_shader_test: partial, *, strip: bool
) -> None:
    result = compile_shader_test(
        {
            "package::main": (
                "import package::missing::value; "
                "@if(enabled) @test fn selected() {} "
                "fn unrelated() { value(); }"
            ),
        },
        options=wesl.TestOptions(
            strip=strip, features=wesl.Features(flags={"enabled": False})
        ),
        dependencies={},
    )
    assert result is None


@pytest.mark.parametrize("registration", ["directory", "modules"])
def test_shader_tests_reject_scoped_assertion_overrides(
    tmp_path: Path, compile_shader_test: partial, wgsl_test: Path, registration: str
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
        compile_shader_test(modules, dependencies=dependencies)


def test_shader_tests_reject_assertions_with_missing_parameters(
    compile_shader_test: partial,
) -> None:
    source = "fn expectCustom(value: u32) {}"
    with pytest.raises(wesl.CompileError, match="shader assertions require") as caught:
        compile_shader_test(
            {
                "package::main": (
                    "@test fn selected() { wgsl_test::expectCustom(1u); }"
                ),
                "wgsl_test": source,
            },
            filenames={"wgsl_test": "assertions.wesl"},
        )
    [diagnostic] = caught.value.diagnostics
    assert diagnostic.module == "wgsl_test"
    assert diagnostic.filename == "assertions.wesl"
    assert diagnostic.source == source
    assert diagnostic.span == (0, len(source.encode()))


def test_shader_assertion_types_preserve_source_context(
    compile_shader_test: partial,
) -> None:
    source = (
        "alias Value = vec2<u32>; fn expectCustom(actual: Value, expected: Value) {}"
    )
    with pytest.raises(wesl.CompileError, match="shader assertion values") as caught:
        compile_shader_test(
            {
                "package::main": (
                    "@test fn selected() { wgsl_test::expectCustom(1, 2); }"
                ),
                "wgsl_test": source,
            },
            filenames={"wgsl_test": "assertions.wesl"},
        )
    [diagnostic] = caught.value.diagnostics
    assert diagnostic.module == "wgsl_test"
    assert diagnostic.filename == "assertions.wesl"
    assert diagnostic.source == source
    assert diagnostic.span == (source.index("fn expectCustom"), len(source))


@pytest.mark.parametrize(
    "declarations",
    [
        "alias Value = Value;",
        "alias Value = Other; alias Other = Value;",
        "alias Value = array<Value, 2>;",
        "struct Value { child: Value }",
    ],
    ids=["self-alias", "mutual-alias", "array-alias", "recursive-struct"],
)
def test_shader_assertion_type_cycles_without_validation(
    pytester: pytest.Pytester, wgsl_test: Path, declarations: str
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
            "        wesl.TestOptions(validate=False),\n"
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


@pytest.mark.parametrize(
    "member",
    ["@align(0) extra: u32,", "extra: Nested,", "extra: array<Nested, 2>,"],
    ids=["direct", "nested-struct", "nested-array"],
)
def test_shader_result_rejects_zero_alignment(
    compile_shader_test: partial, wgsl_test: Path, member: str
) -> None:
    source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    source = "struct Nested { @align(0) value: u32 }\n" + source.replace(
        "struct TestResult {", f"struct TestResult {{ {member}"
    )
    with pytest.raises(wesl.CompileError, match="nonzero alignment") as caught:
        compile_shader_test(
            {
                "package::main": "@test fn selected() { wgsl_test::expect(true); }",
                "wgsl_test::TestResult": source,
            },
            filenames={"wgsl_test::TestResult": "results.wesl"},
        )
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.module == "wgsl_test::TestResult"
    assert diagnostic.filename == "results.wesl"
    assert diagnostic.source == source


@pytest.mark.parametrize(
    "function",
    [
        "fn invalid(value: f32) {}",
        "fn invalid() -> f32 { return 1.0; }",
        "@compute @workgroup_size(1) fn invalid() {}",
    ],
    ids=["user-parameter", "return-value", "compute-entry-point"],
)
def test_invalid_signature(compile_shader_test: partial, function: str) -> None:
    with pytest.raises(wesl.CompileError, match="@test requires a function"):
        compile_shader_test({"package::main": "@test " + function}, test_name="invalid")


@pytest.mark.parametrize("enabled", [False, True])
def test_conditional_non_test_definition(
    compile_shader_test: partial, *, enabled: bool
) -> None:
    modules = {
        "package::main": """
            @if(enabled) @test fn selected() { wgsl_test::expect(true); }
            @else fn selected(value: u32) -> u32 { return value; }
        """,
    }
    options = wesl.TestOptions(
        strip=False, features=wesl.Features(flags={"enabled": enabled})
    )
    compiled = compile_shader_test(modules, options=options)
    assert (compiled is not None) is enabled


def test_requires_test_attribute(compile_shader_test: partial) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        compile_shader_test({"package::main": "fn helper() {}"}, test_name="helper")


def test_assertion_wrappers_only_include_referenced_functions(
    compile_shader_test: partial,
) -> None:
    source = (
        "@test fn selected() { wgsl_test::expect(true); wgsl_test::expect(false); }"
    )
    compiled = compile_shader_test(
        {
            "package::main": source,
            "wgsl_test": "fn expect(value: bool) {} fn expectUnused(value: bool) {}",
        },
        options=wesl.TestOptions(strip=False),
    )
    assert compiled is not None
    shader, _, sites, _, _ = compiled
    wesl.check_syntax(shader)
    assert shader.count("fn _1wgsl_test_expect_wesl_test(") == 1
    assert "fn _1wgsl_test_expectUnused(" in shader
    assert "_1wgsl_test_expectUnused_wesl_test" not in shader
    assert [site.source for site in sites] == [source, source]
