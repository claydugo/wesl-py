import xml.etree.ElementTree as ET

import pytest


def test_collect_without_gpu_dependencies(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import sys
        sys.modules["wgpu"] = None
        sys.modules["numpy"] = None
    """)
    pytester.makefile(
        ".wesl",
        test_math="""
        @test fn first() {}
        @if(enabled) @test fn second() {}
        fn helper() {}
    """,
        noise="@test fn ignored() {}",
    )
    result = pytester.runpytest_subprocess("--collect-only", "-q")
    result.stdout.fnmatch_lines(
        ["test_math.wesl::first", "test_math.wesl::second", "*2 tests collected*"]
    )
    assert result.ret == 0


def test_collection_errors(pytester: pytest.Pytester) -> None:
    pytester.makefile(".wesl", test_invalid="@test fn broken(")
    result = pytester.runpytest_subprocess("--collect-only", "-q")
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*test_invalid.wesl*"])


def test_compiler_without_gpu_dependencies(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        wesl_root = shaders
    """)
    pytester.makeconftest("""
        import sys
        from pathlib import Path
        import pytest
        import wesl

        sys.modules["wgpu"] = None
        sys.modules["numpy"] = None

        @pytest.fixture(params=[False, True], ids=["disabled", "enabled"])
        def wesl_options(request):
            return wesl.CompileOptions(
                strip=False,
                features=wesl.Features(flags={"enabled": request.param}),
            )

        @pytest.fixture
        def wesl_modules():
            return {
                "package::settings": (
                    "@if(enabled) fn value() -> u32 { return 7u; } "
                    "@else fn value() -> u32 { return 3u; }"
                ),
                "package::broken": "fn value() -> u32 { return absent; }",
            }

        @pytest.fixture
        def wesl_filenames():
            return {"package::broken": Path("generated/broken.wesl")}

        @pytest.fixture(scope="session")
        def wesl_device():
            pytest.fail("compilation must not request a GPU")
    """)
    shaders = pytester.path / "shaders"
    shaders.mkdir()
    (shaders / "offset.wgsl").write_text("fn offset() -> u32 { return 1u; }")
    (shaders / "main.wesl").write_text("""
        import package::settings::value;
        import package::offset::offset;
        fn main() -> u32 { return value() + offset(); }
    """)
    pytester.makepyfile("""
        import pytest
        import wesl

        def test_file(wesl_compiler, wesl_options, monkeypatch, tmp_path):
            monkeypatch.chdir(tmp_path)
            shader = wesl_compiler.compile_file("main.wesl")
            expected = "7u" if wesl_options.features.flags["enabled"] else "3u"
            assert expected in shader.wgsl
            assert "package::offset" in shader.modules
            assert shader.sources["package::main"].filename.endswith("main.wesl")

        def test_source(wesl_compiler, wesl_options):
            shader = wesl_compiler.compile_source(
                "import package::settings::value; "
                "import package::offset::offset; "
                "fn main() -> u32 { return value() + offset(); }",
                root="package::generated",
                filename="generated.wesl",
            )
            expected = "7u" if wesl_options.features.flags["enabled"] else "3u"
            assert expected in shader.wgsl
            assert "package::offset" in shader.modules
            assert shader.sources["package::generated"].filename == "generated.wesl"

        def test_error(wesl_compiler):
            with pytest.raises(wesl.CompileError) as caught:
                wesl_compiler.compile_source(
                    "import package::broken::value; "
                    "fn main() -> u32 { return value(); }",
                )
            diagnostic = caught.value.diagnostics[0]
            assert diagnostic.filename == "generated/broken.wesl"
            assert diagnostic.source == "fn value() -> u32 { return absent; }"
    """)
    result = pytester.runpytest_subprocess("-v")
    result.assert_outcomes(passed=6)
    result.stdout.fnmatch_lines(["*test_file[[]disabled] PASSED*"])
    result.stdout.fnmatch_lines(["*test_file[[]enabled] PASSED*"])


def test_compiler_override_controls_native_skips(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        @pytest.fixture
        def wesl_compiler():
            return wesl.Compiler(
                options=wesl.CompileOptions(
                    features=wesl.Features(flags={"enabled": False}),
                ),
            )

        @pytest.fixture
        def wesl_options():
            pytest.fail("the compiler fixture provides the options")

        @pytest.fixture(scope="session")
        def wesl_device():
            pytest.fail("disabled tests must not request a GPU")
    """)
    pytester.makefile(".wesl", test_disabled="@if(enabled) @test fn disabled() {}")
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(skipped=1)


@pytest.mark.skipif(
    not hasattr(pytest, "HIDDEN_PARAM"), reason="requires pytest.HIDDEN_PARAM"
)
def test_hidden_parameter_ids(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        def pytest_generate_tests(metafunc):
            metafunc.parametrize(
                "wesl_options",
                [pytest.param(wesl.CompileOptions(), id=pytest.HIDDEN_PARAM)],
            )
    """)
    pytester.makefile(".wesl", test_hidden="@test fn selected() {}")
    result = pytester.runpytest_subprocess("--collect-only", "-q")
    assert result.ret == 0
    assert "test_hidden.wesl::selected" in result.stdout.lines
    assert "test_hidden.wesl::selected[]" not in result.stdout.lines


def test_generate_tests_with_direct_parameters(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        def pytest_generate_tests(metafunc):
            metafunc.parametrize(
                "wesl_options", [wesl.CompileOptions()], ids=["direct"],
            )

        @pytest.fixture
        def wesl_options():
            pytest.fail("direct parameters must replace the fixture")
    """)
    pytester.makefile(".wesl", test_direct="@if(false) @test fn selected() {}")
    result = pytester.runpytest_subprocess("-v")
    result.assert_outcomes(skipped=1)
    assert "test_direct.wesl::selected[direct] SKIPPED" in result.stdout.str()


def test_collection_hook_markers(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.hookimpl(wrapper=True)
        def pytest_pycollect_makeitem(collector):
            items = yield
            if collector.path.suffix == ".wesl":
                for item in items:
                    item.add_marker(pytest.mark.skip(reason="marked by a plugin"))
            return items

        @pytest.fixture
        def wesl_options():
            pytest.fail("marked tests must skip before WESL setup")
    """)
    pytester.makefile(".wesl", test_marked="@test fn selected() {}")
    result = pytester.runpytest_subprocess("-q", "-rs")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*marked by a plugin*"])


def test_collection_hook_state(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        key = pytest.StashKey[str]()
        collected = []

        @pytest.hookimpl(wrapper=True)
        def pytest_pycollect_makeitem(collector):
            items = yield
            if collector.path.suffix == ".wesl":
                for item in items:
                    collected.append(item)
                    item.stash[key] = "configured"
                    item.user_properties.append(("shader", "configured"))
                    item.extra_keyword_matches.add("configured_shader")
            return items

        def pytest_collection_modifyitems(items):
            assert len(items) == 1
            assert items[0] is collected[0]

        @pytest.fixture
        def wesl_options(request):
            assert request.node.stash[key] == "configured"
            yield wesl.CompileOptions()
    """)
    pytester.makefile(".wesl", test_state="@if(false) @test fn disabled() {}")
    result = pytester.runpytest_subprocess(
        "-q", "-k", "configured_shader", "--junitxml=results.xml"
    )
    result.assert_outcomes(skipped=1)
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    property_element = report.find(".//property[@name='shader']")
    assert property_element is not None
    assert property_element.attrib["value"] == "configured"


def test_custom_function_setup(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        from unittest.mock import Mock
        import pytest

        class CustomFunction(pytest.Function):
            def setup(self):
                assert self.name == "enabled"
                self.user_properties.append(("custom_setup", "ran"))
                super().setup()

        @pytest.hookimpl(wrapper=True)
        def pytest_pycollect_makeitem(collector):
            items = yield
            if collector.path.suffix == ".wesl":
                items = [
                    CustomFunction.from_parent(
                        collector, name=item.name, callobj=item.obj,
                    )
                    for item in items
                ]
            return items

        @pytest.fixture
        def wesl_runner(request):
            assert request.node.name == "enabled"
            return Mock()
    """)
    pytester.makefile(
        ".wesl",
        test_custom="""
            @if(false) @test fn disabled() {}
            @test fn enabled() {}
        """,
    )
    result = pytester.runpytest_subprocess("-q", "--junitxml=results.xml")
    result.assert_outcomes(passed=1, skipped=1)
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    property_element = report.find(
        ".//testcase[@name='enabled']/properties/property[@name='custom_setup']"
    )
    assert property_element is not None
    assert property_element.attrib["value"] == "ran"


@pytest.mark.gpu
def test_fixtures_parametrization_and_selection(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import numpy as np
        import pytest
        import wesl
        from wesl.testing import Buffer

        @pytest.fixture(params=[3, 7], ids=["three", "seven"])
        def wesl_resources(request):
            return {(1, 2): Buffer(data=np.array([request.param], dtype=np.uint32))}

        @pytest.fixture
        def wesl_modules():
            return {"library": "fn double(value: u32) -> u32 { return value * 2u; }"}
    """)
    pytester.makefile(
        ".wesl",
        test_math="""
        import library::double;
        import wgsl_test::expectEq;
        @group(1) @binding(2) var<storage, read_write> values: array<u32>;
        @test fn doubling() { expectEq(double(values[0]), values[0] + values[0]); }
        @test fn mutation() { values[0] = 9u; expectEq(values[0], 9u); }
    """,
    )
    result = pytester.runpytest_subprocess(
        "-q", "test_math.wesl::doubling", "-k", "seven"
    )
    result.assert_outcomes(passed=1, deselected=1)
    result = pytester.runpytest_subprocess("-q", "-m", "wesl")
    result.assert_outcomes(passed=4)


@pytest.mark.gpu
@pytest.mark.parametrize("style", ["auto", "line"])
def test_failure_reports_and_junit(pytester: pytest.Pytester, style: str) -> None:
    pytester.makefile(
        ".wesl",
        test_math="""
        import wgsl_test::expectEq;
        @test fn failing() {
            expectEq(4294967295u, 4294967294u);
        }
    """,
    )
    result = pytester.runpytest_subprocess(
        "-q", f"--tb={style}", "--junitxml=results.xml"
    )
    result.assert_outcomes(failed=1)
    if style == "auto":
        result.stdout.fnmatch_lines(
            [
                "*test_math.wesl:3:5: expectEq failed*",
                "*actual:   *4294967295*",
                "*expected: *4294967294*",
            ]
        )
    else:
        result.stdout.fnmatch_lines(["*test_math.wesl:3: expectEq failed*"])
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    case = report.find(".//testcase")
    assert case is not None
    assert case.attrib["name"] == "failing"
    failure = case.find("failure")
    assert failure is not None
    assert "expectEq failed" in failure.attrib["message"]
    assert failure.text is not None
    assert "test_math.wesl:3:5: expectEq failed" in failure.text
    if style == "auto":
        assert "4294967295" in failure.text


@pytest.mark.gpu
@pytest.mark.parametrize("style", ["line", "no", "native", "full-trace"])
def test_failure_traceback_styles(pytester: pytest.Pytester, style: str) -> None:
    pytester.makefile(
        ".wesl",
        test_failure="@test fn failing() { wgsl_test::expect(false); }",
    )
    result = pytester.runpytest_subprocess(
        "-q", "--full-trace" if style == "full-trace" else f"--tb={style}"
    )
    result.assert_outcomes(failed=1)
    if style == "line":
        result.stdout.fnmatch_lines(["*test_failure.wesl:1: expect failed"])
        assert (
            sum(
                line.endswith("test_failure.wesl:1: expect failed")
                for line in result.stdout.lines
            )
            == 1
        )
        assert "actual:" not in result.stdout.str()
        assert "All traceback entries are hidden" not in result.stdout.str()
    elif style == "no":
        assert "FAILURES" not in result.stdout.str()
        assert "actual:" not in result.stdout.str()
    elif style == "native":
        result.stdout.fnmatch_lines(
            ["*Traceback (most recent call last):*", "*ShaderAssertionError:*"],
        )
    else:
        result.stdout.fnmatch_lines(
            ["*python/wesl/pytest_plugin.py*", "*ShaderAssertionError:*"],
        )


@pytest.mark.gpu
def test_python_failure_uses_pytest_reporting(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        import numpy as np
        import wesl
        from wesl.testing import ShaderAssertionError

        def test_failure():
            raise ShaderAssertionError(
                wesl.Diagnostic("expect", filename="shader.wesl"),
                actual=np.array([False]), expected=np.array([True]),
                failures=1, checks=1, tolerance="",
            )
    """)
    result = pytester.runpytest_subprocess("-q", "--tb=short")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*in test_failure", "*ShaderAssertionError:*"])


@pytest.mark.gpu
def test_skip_xfail_and_conditional_fixtures(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        @pytest.fixture(params=[False, True], ids=["off", "on"])
        def wesl_options(request):
            return wesl.CompileOptions(
                features=wesl.Features(flags={"enabled": request.param}),
            )

        def pytest_collection_modifyitems(items):
            for item in items:
                if item.name.startswith("known_failure"):
                    item.add_marker(
                        pytest.mark.xfail(
                            strict=True, reason="expected shader failure",
                        ),
                    )
                elif item.name.startswith("unavailable"):
                    item.add_marker(pytest.mark.skip(reason="not selected"))
    """)
    pytester.makefile(
        ".wesl",
        test_marks="""
        import wgsl_test::expect;
        @if(enabled) @test fn conditional() { expect(true); }
        @test fn known_failure() { expect(false); }
        @test fn unavailable() { expect(false); }
    """,
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1, skipped=3, xfailed=2)


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("policy", "outcome"), [("required", "errors"), ("optional", "skipped")]
)
def test_unavailable_adapter(
    pytester: pytest.Pytester, policy: str, outcome: str
) -> None:
    pytester.makeconftest("""
        import wgpu

        def unavailable(**kwargs):
            raise RuntimeError("adapter unavailable")

        wgpu.gpu.request_adapter_sync = unavailable
    """)
    pytester.makefile(".wesl", test_adapter="@test fn dispatch() {}")
    result = pytester.runpytest_subprocess("-q", f"--wesl-gpu={policy}")
    result.assert_outcomes(**{outcome: 1})


@pytest.mark.gpu
@pytest.mark.parametrize("style", ["auto", "line"])
def test_xdist(pytester: pytest.Pytester, style: str) -> None:
    pytest.importorskip("xdist")
    pytester.makefile(
        ".wesl",
        test_parallel="""
        import wgsl_test::expectEq;
        @test fn first() { expectEq(1u, 1u); }
        @test fn second() { expectEq(2u, 2u); }
        @test fn third() { expectEq(3u, 3u); }
        @test fn failing() { expectEq(1u, 2u); }
    """,
    )
    result = pytester.runpytest_subprocess(
        "-q", "-n", "2", f"--tb={style}", "--junitxml=results.xml"
    )
    result.assert_outcomes(passed=3, failed=1)
    result.stdout.fnmatch_lines(["*test_parallel.wesl*expectEq failed*"])
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    failure = report.find(".//failure")
    assert failure is not None
    assert failure.attrib["message"] == "expectEq failed"
    assert failure.text is not None
    assert "test_parallel.wesl:5:22: expectEq failed" in failure.text
    if style == "auto":
        assert "actual:" in failure.text


@pytest.mark.gpu
def test_shader_names_do_not_register_hooks(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session", params=["first", "second"])
        def wesl_device(wesl_device):
            return wesl_device
    """)
    pytester.makefile(
        ".wesl",
        test_hooks="""
            @test fn setup_function() { wgsl_test::expect(true); }
            @test fn teardown_function() { wgsl_test::expect(true); }
            @test fn setup_module() { wgsl_test::expect(true); }
            @test fn teardown_module() { wgsl_test::expect(true); }
            @test fn pytest_generate_tests() { wgsl_test::expect(true); }
            @test fn normal() { wgsl_test::expect(true); }
        """,
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=12)


def test_disabled_without_gpu_dependencies(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import sys
        import pytest
        import wesl

        sys.modules["wgpu"] = None
        sys.modules["numpy"] = None

        @pytest.fixture
        def wesl_options():
            return wesl.CompileOptions(
                features=wesl.Features(flags={"enabled": False}),
            )

        @pytest.fixture(scope="session")
        def wesl_device():
            pytest.fail("disabled tests must not request a device")
    """)
    pytester.makefile(
        ".wesl",
        test_disabled="""
            @if(enabled) @test fn conditional() { unavailable::call(); }
            @if(false) @test fn disabled() {}
        """,
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(skipped=2)


@pytest.mark.gpu
def test_named_override_fixture(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.fixture
        def wesl_constants():
            return {"offset": 7}
    """)
    pytester.makefile(
        ".wesl",
        test_override="""
            override offset: u32 = 0u;
            @test fn selected() { wgsl_test::expectEq(offset, 7u); }
        """,
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1)
