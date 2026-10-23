import re
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import pytest
import wesl
from wesl import _native


def _compile_shader_test(
    modules: dict[str, str],
    *,
    options: wesl.TestOptions | None = None,
    filenames: dict[str, str] | None = None,
    dependencies: dict[str, str] | None = None,
) -> object:
    return _native.compile_test(
        wesl.Compiler(
            modules=modules,
            filenames={} if filenames is None else filenames,
            dependencies={} if dependencies is None else dependencies,
        ),
        "package::main",
        "selected",
        wesl.TestOptions() if options is None else options,
        0,
        [],
    )


@pytest.fixture
def compile_shader_test() -> partial:
    return partial(_compile_shader_test)


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
    _native.ParsedTestModule(shader, "compiled.wgsl")
    assert re.search(
        r"@compute\s+@workgroup_size\(8\)\s+fn package_main_unrelated\("
        r"@builtin\(local_invocation_index\) lane: u32\)",
        shader,
    )
    assert f"fn {entry_point}(" in shader


def test_shader_test_error_preserves_source_context(
    compile_shader_test: partial, wgsl_test: Path
) -> None:
    result_source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    result_source, replacement_count = re.subn(
        r"\bfn\s+initTestResult\s*\(\s*\)\s*\{",
        "fn initTestResult() { fail();",
        result_source,
    )
    assert replacement_count == 1
    source = "fn fail() {\n    let café = 1u;\n    let item = missing;\n}\n"
    source += result_source
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


def test_shader_result_evaluates_layout_constants(
    compile_shader_test: partial, wgsl_test: Path
) -> None:
    source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    source = source.replace(
        "expected: vec4f,",
        "@align(alignment) @size(alignment) expected: vec4f, extra: array<u32, count>,",
    )
    source += """
        const alignment = base * 2;
        const count = base / 16;
        const base = 32;
        const unrelated = 1 / 0;
        const_assert false;
    """
    compiled = compile_shader_test(
        {
            "package::main": "@test fn selected() { wgsl_test::expect(true); }",
            "wgsl_test::TestResult": source,
        },
        options=wesl.TestOptions(strip=False),
    )
    assert compiled is not None
    _, _, _, _, layout = compiled
    assert layout.buffer_size == 192


@pytest.mark.parametrize(
    "declarations",
    [
        "alias Value = Value;",
        "alias Value = Other; alias Other = Value;",
        "alias Value = array<Value, 2>;",
        "struct Value { child: Value }",
        "alias Value = array<u32, count>; const count = other; const other = count;",
    ],
    ids=[
        "self-alias",
        "mutual-alias",
        "array-alias",
        "recursive-struct",
        "layout-constant-cycle",
    ],
)
def test_shader_assertion_type_cycles_without_validation(
    pytester: pytest.Pytester, declarations: str
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
            "        wesl.Compiler(\n"
            "            modules={'package::main': '@test fn selected() { "
            "wgsl_test::expectCustom(1, 2); }',\n"
            f"                     'wgsl_test': {source!r}}},\n"
            "            filenames={'wgsl_test': 'assertions.wesl'},\n"
            "        ),\n"
            "        'package::main', 'selected',\n"
            "        wesl.TestOptions(validate=False), 0, [],\n"
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
    source, replacement_count = re.subn(
        r"\bstruct\s+TestResult\s*\{", f"struct TestResult {{ {member}", source
    )
    assert replacement_count == 1
    source = "struct Nested { @align(0) value: u32 }\n" + source
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
    _native.ParsedTestModule(shader, "compiled.wgsl")
    assert len(re.findall(r"\bfn \w*expect_wesl_test\(", shader)) == 1
    assert re.search(r"\bfn \w*expectUnused\(", shader)
    assert not re.search(r"\bfn \w*expectUnused_wesl_test\(", shader)
    assert [site.source for site in sites] == [source, source]


@pytest.mark.parametrize(
    ("modules", "lower", "error_type", "message"),
    [
        (
            {"package::main": "@test fn selected() {}"},
            True,
            NotImplementedError,
            "lowering is not supported",
        ),
        (
            {"package::main": "@test fn selected(value: f32) {}"},
            False,
            wesl.CompileError,
            "@test requires a function",
        ),
        (
            {"package::main": "@test fn selected() -> f32 { return 1.0; }"},
            False,
            wesl.CompileError,
            "@test requires a function",
        ),
        (
            {"package::main": "@test @compute @workgroup_size(1) fn selected() {}"},
            False,
            wesl.CompileError,
            "@test requires a function",
        ),
        (
            {"package::main": "fn selected() {}"},
            False,
            ValueError,
            "does not exist",
        ),
        (
            {
                "package::main": "@test fn selected() { wgsl_test::expectCustom(1u); }",
                "wgsl_test": "fn expectCustom(value: u32) {}",
            },
            False,
            wesl.CompileError,
            "shader assertions require",
        ),
        (
            {
                "package::main": (
                    "@test fn selected() { wgsl_test::expectCustom(1, 2); }"
                ),
                "wgsl_test": (
                    "alias Value = mat2x2f; "
                    "fn expectCustom(actual: Value, expected: Value) {}"
                ),
            },
            False,
            wesl.CompileError,
            "shader assertion values",
        ),
    ],
    ids=[
        "lowering",
        "user-parameter",
        "return-value",
        "compute-entry-point",
        "missing-test-attribute",
        "assertion-without-expected",
        "assertion-value-type",
    ],
)
def test_shader_test_rejections(
    compile_shader_test: partial,
    modules: dict[str, str],
    error_type: type[Exception],
    message: str,
    *,
    lower: bool,
) -> None:
    with pytest.raises(error_type, match=message) as caught:
        compile_shader_test(
            modules,
            options=wesl.TestOptions(lower=lower),
            filenames={"wgsl_test": "assertions.wesl"},
        )
    if "wgsl_test" in modules:
        source = modules["wgsl_test"]
        [diagnostic] = caught.value.diagnostics
        assert diagnostic.module == "wgsl_test"
        assert diagnostic.filename == "assertions.wesl"
        assert diagnostic.source == source
        assert diagnostic.span == (source.index("fn expectCustom"), len(source))


@pytest.mark.parametrize(
    ("source", "enabled", "strip"),
    [
        (
            (
                "import package::missing::value; @if(enabled) @test fn selected() {} "
                "fn unrelated() { value(); }"
            ),
            False,
            False,
        ),
        (
            (
                "import package::missing::value; @if(enabled) @test fn selected() {} "
                "fn unrelated() { value(); }"
            ),
            False,
            True,
        ),
        (
            (
                "@if(enabled) @test fn selected() { wgsl_test::expect(true); } "
                "@else fn selected(value: u32) -> u32 { return value; }"
            ),
            False,
            False,
        ),
        (
            (
                "@if(enabled) @test fn selected() { wgsl_test::expect(true); } "
                "@else fn selected(value: u32) -> u32 { return value; }"
            ),
            True,
            False,
        ),
    ],
    ids=[
        "missing-import-kept",
        "missing-import-stripped",
        "conditional-helper",
        "conditional-test",
    ],
)
def test_conditions_select_shader_tests(
    compile_shader_test: partial,
    wgsl_test: Path,
    source: str,
    *,
    enabled: bool,
    strip: bool,
) -> None:
    compiled = compile_shader_test(
        {"package::main": source},
        options=wesl.TestOptions(
            strip=strip, features=wesl.Features(flags={"enabled": enabled})
        ),
        dependencies={"wgsl_test": str(wgsl_test)} if enabled else {},
    )
    assert (compiled is not None) is enabled


def test_concurrent_shader_instrumentation() -> None:
    def compile_test(index: int) -> tuple[str, wesl.Diagnostic]:
        source = (
            "import wgsl_test::expectEq; "
            f"@test fn test_{index}() {{ expectEq({index}u, {index}u); }}"
        )
        filename = f"shader_{index}.wesl"
        parsed = _native.ParsedTestModule(source, filename)
        [(name, _, _)] = parsed.tests
        assert name == f"test_{index}"
        compiled = _native.compile_test(
            wesl.Compiler(
                modules={"package::main": source}, filenames={"package::main": filename}
            ),
            "package::main",
            name,
            wesl.TestOptions(),
            0,
            [],
            parsed,
        )
        assert compiled is not None
        shader, entry_point, diagnostics, names, _ = compiled
        _native.ParsedTestModule(shader, "compiled.wgsl")
        assert entry_point in shader
        assert "wgsl_test::expectEq" in {
            name
            for compiled_name, name in names.items()
            if compiled_name.endswith("_wesl_test")
        }
        [diagnostic] = diagnostics
        assert filename in _native.render_diagnostic(diagnostic)
        return shader, diagnostic

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(compile_test, range(64)))
    for index, (shader, diagnostic) in enumerate(results):
        assert re.search(rf"\bfn \w*test_{index}\(", shader) is not None
        assert diagnostic.filename == f"shader_{index}.wesl"
        assert diagnostic.message == "expectEq"
        assert diagnostic.source is not None
        assert f"expectEq({index}u, {index}u)" in diagnostic.source
