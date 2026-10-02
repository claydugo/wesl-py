from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import wesl
from wesl import _native


@pytest.mark.parametrize("result_binding", [0, 3])
def test_parsed_module_preserves_syntax_across_compilations(
    wgsl_test: Path,
    result_binding: int,
) -> None:
    source = """
        import wgsl_test::{expectEq as check};
        alias Count = u32;
        struct Value { count: Count, }
        @if(enabled) { fn value() -> Count { return 7u; } }
        @else { fn value() -> Count { return 3u; } }
        override expected: Count = 3u;
        @test fn first() {
            let result = Value(value());
            check(result.count, expected);
        }
        @test fn second() { check(value(), expected); }
    """
    parsed = _native.ParsedTestModule(source, "original.wesl")
    discovered = parsed.tests
    for root, test_name, enabled in [
        ("package::first", "first", False),
        ("package::second", "second", True),
        ("package::first", "first", False),
    ]:
        options = wesl.TestOptions(features=wesl.Features(flags={"enabled": enabled}))
        actual = _native.compile_test(
            {root: source},
            root,
            test_name,
            options,
            {root: "current.wesl"},
            None,
            result_binding,
            {"wgsl_test": str(wgsl_test)},
            parsed,
        )
        expected = _native.compile_test(
            {root: source},
            root,
            test_name,
            options,
            {root: "current.wesl"},
            None,
            result_binding,
            {"wgsl_test": str(wgsl_test)},
        )
        assert actual is not None
        assert expected is not None
        assert sorted(actual[0].split("\n\n")) == sorted(expected[0].split("\n\n"))
        assert actual[1:4] == expected[1:4]
        assert actual[4].buffer_size == expected[4].buffer_size
        assert parsed.tests == discovered
        if result_binding == 0:
            data = _native.execute_test_cpu(
                actual[0],
                actual[1],
                actual[4],
                {actual[3]["expected"]: 7 if enabled else 3},
            )
            result = actual[4].decode(bytes(data))
            assert result.completed == 1
            assert result.passed == 1


@pytest.mark.parametrize("source_location", ["mapping", "filesystem"])
def test_parsed_module_uses_changed_sources(
    wgsl_test: Path,
    tmp_path: Path,
    source_location: str,
) -> None:
    original = "@test fn selected() { wgsl_test::expectEq(1u, 1u); }"
    source = "@test fn selected() { wgsl_test::expectEq(2u, 2u); }"
    parsed = _native.ParsedTestModule(original, "original.wesl")
    (tmp_path / "main.wesl").write_text(source)
    modules = {"package::main": source} if source_location == "mapping" else {}
    actual = _native.compile_test(
        modules,
        "package::main",
        "selected",
        wesl.TestOptions(),
        {},
        str(tmp_path),
        0,
        {"wgsl_test": str(wgsl_test)},
        parsed,
    )
    expected = _native.compile_test(
        modules,
        "package::main",
        "selected",
        wesl.TestOptions(),
        {},
        str(tmp_path),
        0,
        {"wgsl_test": str(wgsl_test)},
    )
    assert actual is not None
    assert expected is not None
    assert sorted(actual[0].split("\n\n")) == sorted(expected[0].split("\n\n"))
    assert actual[1:4] == expected[1:4]


@pytest.mark.parametrize("module_filename", ["package.wesl", "TestResult.wesl"])
def test_assertion_templates_preserve_dependency_overrides(
    wgsl_test: Path,
    tmp_path: Path,
    module_filename: str,
) -> None:
    source = "@test fn selected() { wgsl_test::expectEq(1u, 1u); }"
    _native.compile_test(
        {"package::main": source},
        "package::main",
        "selected",
        wesl.TestOptions(),
        {},
        None,
        0,
        {"wgsl_test": str(wgsl_test)},
    )
    for path in wgsl_test.glob("*.wesl"):
        (tmp_path / path.name).write_text(path.read_text())
    overridden = tmp_path / module_filename
    overridden.write_text(overridden.read_text() + "\nfn invalid(\n")
    with pytest.raises(wesl.CompileError) as caught:
        _native.compile_test(
            {"package::main": source},
            "package::main",
            "selected",
            wesl.TestOptions(),
            {},
            None,
            0,
            {"wgsl_test": str(tmp_path)},
        )
    assert caught.value.diagnostics[0].filename == str(overridden)


def test_parsed_module_supports_concurrent_compilations(wgsl_test: Path) -> None:
    source = "@test fn selected() { wgsl_test::expectEq(7u, 7u); }"
    parsed = _native.ParsedTestModule(source, "original.wesl")
    with ThreadPoolExecutor(max_workers=8) as executor:
        pending = [
            executor.submit(
                _native.compile_test,
                {"package::main": source},
                "package::main",
                "selected",
                wesl.TestOptions(),
                {},
                None,
                result_binding,
                {"wgsl_test": str(wgsl_test)},
                parsed,
            )
            for result_binding in range(16)
        ]
        for result_binding, future in enumerate(pending):
            compiled = future.result()
            assert compiled is not None
            assert f"@binding({result_binding}u)" in compiled[0]
            _native.check_syntax(compiled[0], "compiled.wgsl")
    assert [name for name, start, end in parsed.tests] == ["selected"]
