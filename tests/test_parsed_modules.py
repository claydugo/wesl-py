from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import wesl
from wesl import _native


def test_parsed_module_preserves_syntax_across_compilations() -> None:
    source = """
        import wgsl_test::{expectEq as check};
        alias Count = u32;
        struct Value { count: Count, }
        @if(enabled) { fn value() -> Count { return 7u; } }
        @else { fn value() -> Count { return 3u; } }
        @if(enabled) const expected: Count = 7u;
        @else const expected: Count = 3u;
        @test fn first() {
            let result = Value(value());
            check(result.count, expected);
        }
        @test fn second() { check(value(), expected); }
    """
    parsed = _native.ParsedTestModule(source, "original.wesl")
    discovered = parsed.tests
    for result_binding, root, test_name, enabled in [
        (0, "package::first", "first", False),
        (0, "package::second", "second", True),
        (3, "package::first", "first", False),
        (3, "package::second", "second", True),
    ]:
        options = wesl.TestOptions(features=wesl.Features(flags={"enabled": enabled}))
        arguments = (
            wesl.Compiler(modules={root: source}, filenames={root: "current.wesl"}),
            root,
            test_name,
            options,
            result_binding,
            [],
        )
        actual = _native.compile_test(*arguments, parsed)
        expected = _native.compile_test(*arguments)
        assert actual is not None
        assert expected is not None
        assert sorted(actual[0].split("\n\n")) == sorted(expected[0].split("\n\n"))
        assert actual[1:4] == expected[1:4]
        assert actual[4].buffer_size == expected[4].buffer_size
        assert parsed.tests == discovered
        if result_binding == 0:
            data = _native.execute_test_cpu(actual[0], actual[1], actual[4])
            result = actual[4].decode(bytes(data))
            assert result.completed == 1
            assert result.passed == 1


def test_parsed_module_uses_changed_sources(tmp_path: Path) -> None:
    original = "@test fn selected() { wgsl_test::expectEq(1u, 1u); }"
    source = "@test fn selected() { wgsl_test::expectEq(2u, 2u); }"
    parsed = _native.ParsedTestModule(original, "original.wesl")
    (tmp_path / "main.wesl").write_text(source)
    for modules in [{"package::main": source}, {}]:
        arguments = (
            wesl.Compiler(modules=modules, root_directory=tmp_path),
            "package::main",
            "selected",
            wesl.TestOptions(),
            0,
            [],
        )
        actual = _native.compile_test(*arguments, parsed)
        expected = _native.compile_test(*arguments)
        assert actual is not None
        assert expected is not None
        assert sorted(actual[0].split("\n\n")) == sorted(expected[0].split("\n\n"))
        assert actual[1:4] == expected[1:4]


def test_assertion_templates_preserve_dependency_overrides(
    wgsl_test: Path, tmp_path: Path
) -> None:
    source = "@test fn selected() { wgsl_test::expectEq(1u, 1u); }"
    arguments = ("package::main", "selected", wesl.TestOptions(), 0, [])
    _native.compile_test(
        wesl.Compiler(
            modules={"package::main": source},
            dependencies={"wgsl_test": wgsl_test},
        ),
        *arguments,
    )
    for module_filename in ["package.wesl", "TestResult.wesl"]:
        overrides = tmp_path / module_filename.removesuffix(".wesl")
        overrides.mkdir()
        for path in wgsl_test.glob("*.wesl"):
            (overrides / path.name).write_text(path.read_text())
        overridden = overrides / module_filename
        overridden.write_text(overridden.read_text() + "\nfn invalid(\n")
        with pytest.raises(wesl.CompileError) as caught:
            _native.compile_test(
                wesl.Compiler(
                    modules={"package::main": source},
                    dependencies={"wgsl_test": overrides},
                ),
                *arguments,
            )
        assert caught.value.diagnostics[0].filename == str(overridden)


def test_parsed_module_supports_concurrent_compilations() -> None:
    source = "@test fn selected() { wgsl_test::expectEq(7u, 7u); }"
    parsed = _native.ParsedTestModule(source, "original.wesl")
    with ThreadPoolExecutor(max_workers=8) as executor:
        pending = [
            executor.submit(
                _native.compile_test,
                wesl.Compiler(modules={"package::main": source}),
                "package::main",
                "selected",
                wesl.TestOptions(),
                result_binding,
                [],
                parsed,
            )
            for result_binding in range(16)
        ]
        for result_binding, future in enumerate(pending):
            compiled = future.result()
            assert compiled is not None
            assert f"@binding({result_binding}u)" in compiled[0]
            _native.ParsedTestModule(compiled[0], "compiled.wgsl")
    assert [name for name, start, end in parsed.tests] == ["selected"]
