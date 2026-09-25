import sys
import xml.etree.ElementTree as ET
from importlib.util import find_spec

import pytest


@pytest.mark.skipif(
    find_spec("wgpu") is not None or find_spec("numpy") is not None,
    reason="requires an environment without GPU dependencies",
)
def test_collect_without_gpu_dependencies(pytester: pytest.Pytester) -> None:
    pytester.makefile(
        ".test.wesl",
        math="""
        @test fn first() {}
        @if(enabled) @test fn second() {}
        fn helper() {}
    """,
    )
    pytester.makefile(
        ".wesl",
        noise="@test fn ignored() {}",
        test_prefix="@test fn ignored() {}",
        suffix_test="@test fn ignored() {}",
    )
    result = pytester.runpytest_subprocess("--collect-only", "-q")
    result.stdout.fnmatch_lines(
        ["math.test.wesl::first", "math.test.wesl::second", "*2 tests collected*"]
    )
    assert result.ret == 0
    result = pytester.runpytest_subprocess("--collect-only", "-q", "-m", "not gpu")
    result.stdout.fnmatch_lines(["*2 deselected*"])
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
    result = pytester.runpytest_subprocess("--collect-only", "-q", "noise.wesl")
    result.stdout.fnmatch_lines(["noise.wesl::ignored", "*1 test collected*"])
    assert result.ret == 0


@pytest.mark.gpu
@pytest.mark.parametrize("manifest", [False, True])
def test_compilation_and_shader_tests_share_project_settings(
    pytester: pytest.Pytester, *, manifest: bool
) -> None:
    if manifest:
        pytester.makefile(".toml", wesl='edition = "2026_pre"\nroot = "shaders"\n')
    shaders = pytester.path / "shaders"
    shaders.mkdir()
    (shaders / "exposure.wesl").write_text(
        "@if(enabled) fn exposure() -> u32 { return 7u; } "
        "@else fn exposure() -> u32 { return 3u; }"
    )
    (shaders / "main.wesl").write_text(
        "import package::exposure::exposure; "
        "@compute @workgroup_size(1) fn main() { let result = exposure(); }"
    )
    (shaders / "exposure.test.wesl").write_text(
        "import package::exposure::exposure; "
        "@test fn result() { "
        "@if(enabled) wgsl_test::expectEq(exposure(), 7u); "
        "@else wgsl_test::expectEq(exposure(), 3u); }"
    )
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(params=[False, True])
        def wesl_features(request):
            return {"enabled": request.param}
    """)
    (shaders / "test_compile.py").write_text("""
import wesl

def test_compile(wesl_compiler, wesl_features):
    result = wesl_compiler.compile_file("main.wesl")
    expected = "7u" if wesl_features["enabled"] else "3u"
    assert expected in result.wgsl
    assert result == wesl.compile_file(
        "shaders/main.wesl", features=wesl_features
    )
""")
    result = pytester.runpytest_subprocess("shaders", "-q")
    result.assert_outcomes(passed=4)


def test_options_import_does_not_collect_class(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        from wesl import TestOptions

        def test_options():
            TestOptions()
    """)
    result = pytester.runpytest_subprocess("-q", "-W", "error")
    result.assert_outcomes(passed=1)


@pytest.mark.gpu
def test_shader_tests_load_manifest_dependencies(pytester: pytest.Pytester) -> None:
    pytester.makefile(
        ".toml",
        wesl='edition = "2026_pre"\nroot = "shaders"\n'
        '[dependencies]\nlibrary = { path = "library" }\n',
    )
    shaders = pytester.path / "shaders"
    shaders.mkdir()
    library = pytester.path / "library"
    (library / "src").mkdir(parents=True)
    (library / "wesl.toml").write_text('edition = "2026_pre"\nroot = "src"\n')
    (library / "src/package.wesl").write_text("fn value() -> u32 { return 7u; }")
    (shaders / "library.test.wesl").write_text(
        "@test fn imported() { wgsl_test::expectEq(library::value(), 7u); }"
    )
    result = pytester.runpytest_subprocess("shaders", "-q")
    result.assert_outcomes(passed=1)


@pytest.mark.gpu
def test_dependency_fixture_overrides_missing_manifest_paths(
    pytester: pytest.Pytester,
) -> None:
    pytester.makefile(
        ".toml",
        wesl='edition = "2026_pre"\nroot = "shaders"\n'
        '[dependencies]\nlibrary = { path = "unavailable" }\n',
    )
    pytester.makeconftest("""
        from pathlib import Path
        import pytest

        @pytest.fixture
        def wesl_dependencies():
            return {"library": Path(__file__).parent / "replacement"}
    """)
    shaders = pytester.path / "shaders"
    shaders.mkdir()
    replacement = pytester.path / "replacement"
    replacement.mkdir()
    (replacement / "package.wesl").write_text("fn value() -> u32 { return 7u; }")
    (shaders / "library.test.wesl").write_text(
        "@test fn imported() { wgsl_test::expectEq(library::value(), 7u); }"
    )
    (shaders / "test_compile.py").write_text("""
def test_compile(wesl_compiler):
    result = wesl_compiler.compile_file("main.wesl")
    assert "7u" in result.wgsl
""")
    (shaders / "main.wesl").write_text(
        "@compute @workgroup_size(1) fn main() { let value = library::value(); }"
    )
    result = pytester.runpytest_subprocess("shaders", "-q")
    result.assert_outcomes(passed=2)


@pytest.mark.gpu
def test_shader_tests_share_transitive_dependency_state(
    pytester: pytest.Pytester,
) -> None:
    pytester.makefile(
        ".toml",
        wesl='edition = "2026_pre"\nroot = "."\n'
        '[dependencies]\nalpha = { path = "alpha" }\nbeta = { path = "beta" }\n',
    )
    for name in ("alpha", "beta"):
        directory = pytester.path / name
        directory.mkdir()
        (directory / "wesl.toml").write_text(
            'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
            'common = { path = "../common" }\n'
        )
        (directory / "package.wesl").write_text(
            "import {common::next}; fn value() -> u32 { return next(); }"
        )
    common = pytester.path / "common"
    common.mkdir()
    (common / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (common / "package.wesl").write_text(
        "var<private> counter: u32 = 0u; "
        "fn next() -> u32 { counter += 1u; return counter; }"
    )
    pytester.makefile(
        ".test.wesl",
        shared_state="@test fn shared_state() { "
        "wgsl_test::expectEq(alpha::value(), 1u); "
        "wgsl_test::expectEq(beta::value(), 2u); }",
    )
    result = pytester.runpytest_subprocess("shared_state.test.wesl", "-q")
    result.assert_outcomes(passed=1)


def test_collection_errors(pytester: pytest.Pytester) -> None:
    pytester.makefile(".test.wesl", invalid="@test fn broken(")
    result = pytester.runpytest_subprocess("--collect-only", "-q")
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*invalid.test.wesl*"])


@pytest.mark.gpu
def test_root_with_parent_components(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        wesl_root = shaders/..
    """)
    pytester.makeconftest("""
        import pytest

        @pytest.fixture
        def wesl_root_directory(wesl_root_directory, pytestconfig):
            assert wesl_root_directory == pytestconfig.rootpath
            return wesl_root_directory / "shaders/.."
    """)
    pytester.makefile(".wesl", helper="fn value() -> u32 { return 7u; }")
    pytester.makefile(
        ".test.wesl",
        **{
            "shaders/math": """
                import package::helper::value;
                @test fn selected() { wgsl_test::expectEq(value(), 7u); }
            """,
        },
    )
    result = pytester.runpytest_subprocess("shaders", "-q")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(
    sys.platform == "win32", reason="Symlinks require Windows privileges."
)
@pytest.mark.gpu
def test_symlink_root_preserves_relative_imports(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        wesl_root = linked
    """)
    shaders = pytester.path / "shaders"
    (shaders / "nested").mkdir(parents=True)
    (shaders / "nested/helper.wesl").write_text("fn value() -> u32 { return 7u; }")
    source = pytester.makefile(
        ".wesl",
        source="""
            import super::helper::value;
            @test fn selected() { wgsl_test::expectEq(value(), 7u); }
        """,
    )
    (shaders / "nested/math.test.wesl").symlink_to(source)
    (pytester.path / "linked").symlink_to(shaders, target_is_directory=True)
    result = pytester.runpytest_subprocess("linked", "-q")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(
    find_spec("wgpu") is not None or find_spec("numpy") is not None,
    reason="requires an environment without GPU dependencies",
)
def test_compiler_without_gpu_dependencies(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        wesl_root = shaders
    """)
    pytester.makeconftest("""
        from pathlib import Path
        import pytest
        import wesl

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
                "package::broken": "fn value() -> u32 { return ; ) }",
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
        from contextlib import chdir
        from pathlib import Path
        import pytest
        import wesl

        def test_file(wesl_compiler, wesl_options, tmp_path):
            with chdir(tmp_path):
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
            assert diagnostic.filename == str(Path("generated/broken.wesl"))
            assert diagnostic.source == "fn value() -> u32 { return ; ) }"
    """)
    result = pytester.runpytest_subprocess("-v")
    result.assert_outcomes(passed=6)
    result.stdout.fnmatch_lines(["*test_file[[]disabled] PASSED*"])
    result.stdout.fnmatch_lines(["*test_file[[]enabled] PASSED*"])


@pytest.mark.gpu
def test_shared_features_and_independent_options(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        @pytest.fixture(params=[False, True], ids=["off", "on"])
        def wesl_features(request):
            return wesl.Features(flags={"enabled": request.param})

        @pytest.fixture
        def wesl_options(wesl_features):
            return wesl.CompileOptions(
                keep=["selected"],
                mangler=wesl.ManglerKind.Hash,
                sourcemap=False,
                features=wesl_features,
            )

        @pytest.fixture
        def wesl_test_options(wesl_features):
            return wesl.TestOptions(lower=True, features=wesl_features)

        @pytest.fixture
        def wesl_constants(wesl_features):
            return {"expected": 7 if wesl_features.flags["enabled"] else 3}
    """)
    pytester.makefile(
        ".test.wesl",
        shared="""
            override expected: u32;
            @if(enabled) fn value() -> u32 { return 7u; }
            @else fn value() -> u32 { return 3u; }
            @test fn selected() { wgsl_test::expectEq(value(), expected); }
        """,
    )
    pytester.makepyfile("""
        def test_features(wesl_compiler, wesl_features, wesl_test_options):
            assert wesl_compiler.options.features is wesl_features
            assert wesl_test_options.features is wesl_features
            shader = wesl_compiler.compile_source(
                "@if(enabled) fn selected() -> u32 { return 7u; } "
                "@else fn selected() -> u32 { return 3u; }",
            )
            expected = "7u" if wesl_features.flags["enabled"] else "3u"
            assert expected in shader.wgsl
            assert not shader.sources
    """)
    result = pytester.runpytest_subprocess("-v")
    result.assert_outcomes(passed=4)
    result.stdout.fnmatch_lines(
        ["*shared.test.wesl::selected[[]off] PASSED*", "*selected[[]on] PASSED*"],
    )


@pytest.mark.gpu
def test_test_options_control_native_skips(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        @pytest.fixture
        def wesl_test_options():
            return wesl.TestOptions(
                features=wesl.Features(flags={"enabled": False}),
            )

        @pytest.fixture
        def wesl_options():
            pytest.fail("native tests must not request compilation options")

        @pytest.fixture
        def wesl_compiler():
            pytest.fail("native tests must not request the compiler fixture")

    """)
    pytester.makefile(".test.wesl", disabled="@if(enabled) @test fn disabled() {}")
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(skipped=1)


def test_setup_plan_does_not_execute_fixtures(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def wesl_device():
            pytest.fail("setup planning must not create a device")

        @pytest.fixture
        def wesl_test_options():
            pytest.fail("setup planning must not evaluate test options")

        @pytest.fixture(params=[1, 2])
        def wesl_resources(request):
            pytest.fail("setup planning must not allocate resources")
    """)
    pytester.makefile(
        ".test.wesl",
        plan="@test fn enabled() {} @if(false) @test fn disabled() {}",
    )
    result = pytester.runpytest_subprocess("--setup-plan", "-q")
    assert result.ret == 0
    result.stdout.fnmatch_lines(
        [
            "*SETUP*S wesl_device*",
            "*SETUP*F wesl_resources[[]1]*",
            "*plan.test.wesl::enabled[[]1]*",
            "*plan.test.wesl::enabled[[]2]*",
            "*plan.test.wesl::disabled[[]1]*",
            "*plan.test.wesl::disabled[[]2]*",
        ],
    )


def test_disabled_tests_defer_resource_fixtures(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(params=[False, True], ids=["off", "on"])
        def wesl_features(request):
            return {"enabled": request.param}

        @pytest.fixture(scope="session", params=[1, 2])
        def device_configuration(request):
            pytest.fail("disabled tests must not initialize device dependencies")

        @pytest.fixture(scope="session")
        def wesl_device(device_configuration):
            pytest.fail("disabled tests must not initialize the device")

        @pytest.fixture(params=[3, 7])
        def wesl_resources(request, wesl_device):
            pytest.fail("disabled tests must not allocate resources")

        @pytest.fixture
        def wesl_constants():
            pytest.fail("disabled tests must not request constants")
    """)
    pytester.makefile(
        ".test.wesl",
        disabled="""
            import missing::value;
            @if(enabled) { @test fn selected() {} }
            @elif(false) @test fn selected() {}
            @else @test fn fallback() {}
        """,
    )
    result = pytester.runpytest_subprocess("-q", "-k", "selected and off")
    result.assert_outcomes(skipped=4, deselected=12)
    result = pytester.runpytest_subprocess("-q", "-k", "fallback and on")
    result.assert_outcomes(skipped=4, deselected=12)


@pytest.mark.gpu
def test_fixture_names_remain_visible_during_setup(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.fixture
        def wesl_features(request):
            return {"enabled": "wesl_resources" in request.fixturenames}
    """)
    pytester.makefile(
        ".test.wesl",
        names="@if(enabled) @test fn selected() { wgsl_test::expect(true); }",
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1)


def test_disabled_tests_preserve_explicit_fixtures(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        events = []

        @pytest.fixture(scope="session", autouse=True)
        def wesl_device():
            events.append("device")
            yield object()
            assert set(events) == {"device", "resources", "constants", "released"}

        @pytest.fixture
        def wesl_resources():
            events.append("resources")
            yield {}
            events.append("released")

        @pytest.fixture
        def wesl_test_options(wesl_resources):
            assert "resources" in events
            return wesl.TestOptions()

        @pytest.fixture
        def wesl_constants():
            events.append("constants")
            return {}

        def pytest_collection_modifyitems(items):
            for item in items:
                item.add_marker(pytest.mark.usefixtures("wesl_constants"))
    """)
    pytester.makefile(".test.wesl", disabled="@if(false) @test fn disabled() {}")
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
                "wesl_test_options",
                [pytest.param(wesl.TestOptions(), id=pytest.HIDDEN_PARAM)],
            )
    """)
    pytester.makefile(".test.wesl", hidden="@test fn selected() {}")
    result = pytester.runpytest_subprocess("--collect-only", "-q")
    assert result.ret == 0
    assert "hidden.test.wesl::selected" in result.stdout.lines
    assert "hidden.test.wesl::selected[]" not in result.stdout.lines


@pytest.mark.gpu
def test_generate_tests_with_direct_parameters(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        def pytest_generate_tests(metafunc):
            metafunc.parametrize(
                "wesl_test_options", [wesl.TestOptions()], ids=["direct"],
            )

        @pytest.fixture
        def wesl_test_options():
            pytest.fail("direct parameters must replace the fixture")
    """)
    pytester.makefile(".test.wesl", direct="@if(false) @test fn selected() {}")
    result = pytester.runpytest_subprocess("-v")
    result.assert_outcomes(skipped=1)
    assert "direct.test.wesl::selected[direct] SKIPPED" in result.stdout.str()


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
        def wesl_test_options():
            pytest.fail("marked tests must skip before WESL setup")
    """)
    pytester.makefile(".test.wesl", marked="@test fn selected() {}")
    result = pytester.runpytest_subprocess("-q", "-rs")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*marked by a plugin*"])


@pytest.mark.gpu
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
                    assert item.location[2] == item.name
                    item.stash[key] = "configured"
                    item.user_properties.append(("shader", "configured"))
                    item.extra_keyword_matches.add("configured_shader")
            return items

        def pytest_collection_modifyitems(items):
            assert len(items) == 1
            assert items[0] is collected[0]
            assert items[0].location == ("state.test.wesl", 0, "disabled")

        @pytest.fixture
        def wesl_test_options(request):
            assert request.node.stash[key] == "configured"
            yield wesl.TestOptions()
    """)
    pytester.makefile(".test.wesl", state="@if(false) @test fn disabled() {}")
    result = pytester.runpytest_subprocess(
        "-q",
        "-k",
        "configured_shader",
        "--junitxml=results.xml",
        "-o",
        "junit_family=xunit1",
    )
    result.assert_outcomes(skipped=1)
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    case = report.find(".//testcase")
    assert case is not None
    assert case.attrib["file"] == "state.test.wesl"
    assert case.attrib["line"] == "0"
    property_element = report.find(".//property[@name='shader']")
    assert property_element is not None
    assert property_element.attrib["value"] == "configured"


@pytest.mark.gpu
def test_custom_function_setup(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        class CustomFunction(pytest.Function):
            def setup(self):
                self.user_properties.append(("custom_setup", "ran"))
                super().setup()
                assert self.funcargs["wesl_resources"] == {}

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

        @pytest.fixture(autouse=True)
        def configure(request):
            assert ("custom_setup", "ran") in request.node.user_properties

        @pytest.fixture
        def wesl_resources(request):
            assert ("custom_setup", "ran") in request.node.user_properties
            return {}
    """)
    pytester.makefile(
        ".test.wesl",
        custom="""
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
        from struct import pack
        import pytest
        import wesl
        import wgpu

        @pytest.fixture(params=[3, 7], ids=["three", "seven"])
        def wesl_resources(request, wesl_device):
            buffer = wesl_device.create_buffer_with_data(
                data=pack("<I", request.param), usage=wgpu.BufferUsage.STORAGE,
            )
            try:
                yield {1: [{"binding": 2, "resource": {"buffer": buffer}}]}
            finally:
                buffer.destroy()

        @pytest.fixture
        def wesl_modules():
            return {
                "library": "fn double(value: u32) -> u32 { return value * 2u; }"
            }
    """)
    pytester.makefile(
        ".test.wesl",
        math="""
        import library::double;
        import wgsl_test::expectEq;
        @group(1) @binding(2) var<storage, read_write> values: array<u32>;
        @test fn doubling() { expectEq(double(values[0]), values[0] + values[0]); }
        @test fn mutation() { values[0] = 9u; expectEq(values[0], 9u); }
    """,
    )
    result = pytester.runpytest_subprocess(
        "-q", "math.test.wesl::doubling", "-k", "seven"
    )
    result.assert_outcomes(passed=1, deselected=1)
    result = pytester.runpytest_subprocess("-q", "-m", "wesl")
    result.assert_outcomes(passed=4)


@pytest.mark.gpu
@pytest.mark.parametrize("style", ["auto", "line"])
@pytest.mark.parametrize("color", ["yes", "no"])
def test_failure_reports_and_junit(
    pytester: pytest.Pytester, style: str, color: str
) -> None:
    pytester.makefile(
        ".test.wesl",
        math="""
        import wgsl_test::expectEq;
        @test fn failing() {
            expectEq(4294967295u, 4294967294u);
        }
    """,
    )
    result = pytester.runpytest_subprocess(
        "-q", f"--tb={style}", f"--color={color}", "--junitxml=results.xml"
    )
    result.assert_outcomes(failed=1)
    if style == "auto":
        result.stdout.fnmatch_lines(
            [
                "*math.test.wesl:3:5: expectEq failed*",
                "*actual:   *4294967295u*",
                "*expected: *4294967294u*",
            ]
        )
    else:
        result.stdout.fnmatch_lines(["*math.test.wesl:3: expectEq failed"])
        assert (
            sum(
                line.endswith("math.test.wesl:3: expectEq failed")
                for line in result.stdout.lines
            )
            == 1
        )
        assert "actual:" not in result.stdout.str()
        assert "All traceback entries are hidden" not in result.stdout.str()
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    case = report.find(".//testcase")
    assert case is not None
    assert case.attrib["name"] == "failing"
    failure = case.find("failure")
    assert failure is not None
    assert "expectEq failed" in failure.attrib["message"]
    assert failure.text is not None
    assert "\x1b" not in failure.text
    assert str(pytester.path) not in failure.text
    assert "math.test.wesl:3:5: expectEq failed" in failure.text
    if style == "auto":
        assert "4294967295" in failure.text
        assert "3 |     expectEq(4294967295u, 4294967294u);" in failure.text
        assert "1 of 1 assertions failed" in failure.text
        if color == "yes":
            assert "\x1b[31m4294967295u\x1b[0m" in result.stdout.str()
            assert "\x1b[32m4294967294u\x1b[0m" in result.stdout.str()
    if color == "no":
        assert "\x1b" not in result.stdout.str()


@pytest.mark.gpu
@pytest.mark.parametrize("workers", [0, 2])
def test_failure_notes(pytester: pytest.Pytester, workers: int) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.hookimpl(wrapper=True)
        def pytest_runtest_call(item):
            try:
                return (yield)
            except AssertionError as error:
                error.add_note("  expected: extra diagnostic")
                error.add_note("  actual: vec2f(1.0, 2.0)")
                error.add_note("  expected: false")
                error.add_note("  actual: extra diagnostic")
                raise
    """)
    pytester.makefile(
        ".test.wesl",
        failure="@test fn failing() { wgsl_test::expect(false); }",
    )
    result = pytester.runpytest_subprocess(
        "-q", "-n", str(workers), "--color=yes", "--junitxml=results.xml"
    )
    result.assert_outcomes(failed=1)
    assert "\x1b[31mfalse\x1b[0m" in result.stdout.str()
    assert "\x1b[32mtrue\x1b[0m" in result.stdout.str()
    assert (
        "  expected: extra diagnostic\n"
        "  actual: vec2f(1.0, 2.0)\n"
        "  expected: false\n"
        "  actual: extra diagnostic\n"
    ) in result.stdout.str()
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    failure = report.find(".//failure")
    assert failure is not None
    assert failure.text is not None
    assert "  actual: extra diagnostic" in failure.text
    assert "\x1b" not in failure.text


@pytest.mark.gpu
def test_vector_failure_color_and_project_root(pytester: pytest.Pytester) -> None:
    pytester.makeini("[pytest]\nwesl_root = shaders")
    directory = pytester.path / "shaders"
    directory.mkdir()
    filename = directory / "vector.test.wesl"
    filename.write_text(
        "@test fn failing() { "
        "wgsl_test::expectNearVec3(vec3f(1.0, 0.0, 0.0), vec3f(2.0, 0.0, 0.0)); }"
    )
    result = pytester.runpytest_subprocess(
        "-q", "--color=yes", "--junitxml=results.xml"
    )
    result.assert_outcomes(failed=1)
    assert "vec3f(\x1b[31m1.0\x1b[0m, 0.0, 0.0)" in result.stdout.str()
    assert "vec3f(\x1b[32m2.0\x1b[0m, 0.0, 0.0)" in result.stdout.str()
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    failure = report.find(".//failure")
    assert failure is not None
    assert failure.text is not None
    assert f"{filename.relative_to(pytester.path)}:1:22:" in failure.text
    assert "\x1b" not in failure.text


@pytest.mark.gpu
@pytest.mark.parametrize("style", ["no", "native", "full-trace"])
def test_failure_traceback_styles(pytester: pytest.Pytester, style: str) -> None:
    pytester.makefile(
        ".test.wesl",
        failure="@test fn failing() { wgsl_test::expect(false); }",
    )
    result = pytester.runpytest_subprocess(
        "-q", "--full-trace" if style == "full-trace" else f"--tb={style}"
    )
    result.assert_outcomes(failed=1)
    if style == "no":
        assert "FAILURES" not in result.stdout.str()
        assert "actual:" not in result.stdout.str()
    elif style == "native":
        result.stdout.fnmatch_lines(
            ["*Traceback (most recent call last):*", "*ShaderAssertionError:*"],
        )
    else:
        result.stdout.fnmatch_lines(
            ["*wesl?pytest_plugin.py*", "*ShaderAssertionError:*"],
        )


@pytest.mark.skipif(
    find_spec("wgpu") is None,
    reason="requires wesl-py[testing]",
)
def test_python_failure_uses_pytest_reporting(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        import wesl
        from wesl.testing import ShaderAssertionError

        def test_failure():
            raise ShaderAssertionError(
                wesl.Diagnostic("expect", filename="shader.wesl"),
                actual=False, expected=True,
                failures=1, checks=1,
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
        def wesl_features(request):
            return wesl.Features(flags={"enabled": request.param})

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
        ".test.wesl",
        marks="""
        import wgsl_test::expect;
        @if(enabled) @test fn conditional() { expect(true); }
        @test fn known_failure() { expect(false); }
        @test fn unavailable() { expect(false); }
    """,
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1, skipped=3, xfailed=2)


@pytest.mark.skipif(
    find_spec("wgpu") is not None,
    reason="requires an environment without wgpu",
)
@pytest.mark.parametrize(
    ("policy", "outcome"), [("required", "errors"), ("optional", "skipped")]
)
def test_missing_gpu_dependency_policy(
    pytester: pytest.Pytester, policy: str, outcome: str
) -> None:
    pytester.makefile(".test.wesl", adapter="@test fn dispatch() {}")
    result = pytester.runpytest_subprocess("-q", "-ra", f"--wesl-gpu={policy}")
    result.assert_outcomes(**{outcome: 1})
    assert "install wesl-py[testing] to run shader tests" in result.stdout.str()


@pytest.mark.gpu
@pytest.mark.skipif(sys.platform != "linux", reason="requires the Vulkan loader")
@pytest.mark.parametrize(
    ("policy", "outcome"), [("required", "errors"), ("optional", "skipped")]
)
def test_missing_adapter_policy(
    pytester: pytest.Pytester, policy: str, outcome: str
) -> None:
    pytester.makeconftest("""
        import os
        from pathlib import Path

        os.environ["WGPU_BACKEND_TYPE"] = "Vulkan"
        os.environ["VK_DRIVER_FILES"] = str(Path(__file__).parent / "missing-icd.json")
        os.environ["VK_ICD_FILENAMES"] = str(Path(__file__).parent / "missing-icd.json")
    """)
    pytester.makefile(".test.wesl", adapter="@test fn dispatch() {}")
    result = pytester.runpytest_subprocess("-q", "-ra", f"--wesl-gpu={policy}")
    result.assert_outcomes(**{outcome: 1})


@pytest.mark.gpu
@pytest.mark.parametrize("policy", ["required", "optional"])
def test_device_creation_failure_is_an_error(
    pytester: pytest.Pytester, policy: str
) -> None:
    pytester.makeconftest("""
        from functools import partial

        import pytest
        import wgpu

        @pytest.fixture(scope="session", autouse=True)
        def invalid_device_limits():
            adapter = wgpu.gpu.request_adapter_sync()
            with pytest.MonkeyPatch.context() as monkeypatch:
                monkeypatch.setattr(wgpu.gpu, "request_adapter_sync", lambda: adapter)
                monkeypatch.setattr(
                    adapter,
                    "request_device_sync",
                    partial(
                        adapter.request_device_sync,
                        required_limits={
                            "max-buffer-size": adapter.limits["max-buffer-size"] + 1,
                        },
                    ),
                )
                yield
    """)
    pytester.makefile(".test.wesl", device="@test fn dispatch() {}")
    result = pytester.runpytest_subprocess("-q", "-ra", f"--wesl-gpu={policy}")
    result.assert_outcomes(errors=1)
    assert "max_buffer_size" in result.stdout.str()


@pytest.mark.gpu
@pytest.mark.parametrize("style", ["auto", "line"])
def test_xdist(pytester: pytest.Pytester, style: str) -> None:
    pytest.importorskip("xdist")
    pytester.makefile(
        ".test.wesl",
        parallel="""
        import wgsl_test::expectEq;
        @test fn first() { expectEq(1u, 1u); }
        @test fn second() { expectEq(2u, 2u); }
        @test fn third() { expectEq(3u, 3u); }
        @test fn failing() { expectEq(1u, 2u); }
    """,
    )
    result = pytester.runpytest_subprocess(
        "-q", "-n", "2", f"--tb={style}", "--color=yes", "--junitxml=results.xml"
    )
    result.assert_outcomes(passed=3, failed=1)
    result.stdout.fnmatch_lines(["*parallel.test.wesl*expectEq failed*"])
    report = ET.parse(pytester.path / "results.xml")  # noqa: S314
    failure = report.find(".//failure")
    assert failure is not None
    assert failure.attrib["message"] == "expectEq failed"
    assert failure.text is not None
    assert "\x1b" not in failure.text
    assert "parallel.test.wesl:5:22: expectEq failed" in failure.text
    if style == "auto":
        assert "actual:" in failure.text
        assert "\x1b[31m1u\x1b[0m" in result.stdout.str()
        assert "\x1b[32m2u\x1b[0m" in result.stdout.str()


@pytest.mark.gpu
def test_shader_names_do_not_register_hooks(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session", params=["first", "second"])
        def wesl_device(wesl_device):
            return wesl_device
    """)
    pytester.makefile(
        ".test.wesl",
        hooks="""
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


@pytest.mark.gpu
def test_autouse_fixtures_run_before_test_options(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest
        import wesl

        @pytest.fixture(autouse=True)
        def configure(tmp_path):
            (tmp_path / "configured").write_text("enabled")

        @pytest.fixture
        def wesl_test_options(tmp_path):
            return wesl.TestOptions(
                features=wesl.Features(
                    flags={
                        "enabled": (tmp_path / "configured").read_text() == "enabled",
                    },
                ),
            )
    """)
    pytester.makefile(
        ".test.wesl",
        order="""
            @test fn configured() {
                @if(enabled) wgsl_test::expect(true);
                @else wgsl_test::expect(false);
            }
        """,
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1)
