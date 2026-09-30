import xml.etree.ElementTree as ET

import pytest


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("style", "workers"),
    [("auto", 0), ("line", 0), ("auto", 2)],
    ids=["serial", "short-report", "xdist"],
)
def test_failure_reports_and_junit(
    pytester: pytest.Pytester, style: str, workers: int
) -> None:
    pytester.makeconftest("""
        import pytest

        @pytest.hookimpl(wrapper=True)
        def pytest_runtest_call(item):
            try:
                return (yield)
            except AssertionError as error:
                error.add_note("shader assertion note")
                raise
    """)
    pytester.makefile(
        ".test.wesl",
        math="""
        import wgsl_test::expectEq;
        @test fn failing() {
            expectEq(4294967295u, 4294967294u);
        }
    """,
    )
    if workers:
        pytest.importorskip("xdist")
    result = pytester.runpytest_subprocess(
        "-q",
        f"--tb={style}",
        "--color=yes",
        "--junitxml=results.xml",
        *(["-n", str(workers)] if workers else []),
    )
    result.assert_outcomes(failed=1)
    if style == "auto":
        result.stdout.fnmatch_lines(
            [
                "*error: expectEq failed*",
                "*--> math.test.wesl:3:5",
                "*actual:   *4294967295u*",
                "*expected: *4294967294u*",
                "*shader assertion note*",
            ]
        )
    else:
        result.stdout.fnmatch_lines(["*math.test.wesl:3:5: expectEq failed"])
        assert "actual:" not in result.stdout.str()
        assert "All traceback entries are hidden" not in result.stdout.str()
    report = ET.parse(pytester.path / "results.xml")
    case = report.find(".//testcase")
    assert case is not None
    assert case.attrib["name"] == "failing"
    failure = case.find("failure")
    assert failure is not None
    assert "expectEq failed" in failure.attrib["message"]
    assert failure.text is not None
    assert "\x1b" not in failure.text
    assert str(pytester.path) not in failure.text
    assert "math.test.wesl:3:5" in failure.text
    if style == "auto":
        assert "4294967295" in failure.text
        assert "3 |     expectEq(4294967295u, 4294967294u);" in failure.text
        assert "1 of 1 assertions failed" in failure.text
        assert "shader assertion note" in failure.text


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("raise_statement", "cause_visible"),
    [
        pytest.param("raise error from cause", True, id="explicit-cause"),
        pytest.param("raise error", True, id="implicit-context"),
        pytest.param("raise error from None", False, id="suppressed-context"),
    ],
)
def test_failure_chaining(
    pytester: pytest.Pytester,
    raise_statement: str,
    *,
    cause_visible: bool,
) -> None:
    pytester.makeconftest(f"""
        import pytest
        from wesl.testing import ShaderAssertionError

        @pytest.hookimpl(wrapper=True)
        def pytest_runtest_call(item):
            try:
                return (yield)
            except ShaderAssertionError as error:
                error.add_note("shader assertion note")
                try:
                    raise RuntimeError("shader input failed")
                except RuntimeError as cause:
                    {raise_statement}
    """)
    pytester.makefile(
        ".test.wesl",
        failure="@test fn failing() { wgsl_test::expect(false); }",
    )
    result = pytester.runpytest_subprocess("-q", "--junitxml=results.xml")
    result.assert_outcomes(failed=1)
    assert ("RuntimeError: shader input failed" in result.stdout.str()) is cause_visible
    assert "shader assertion note" in result.stdout.str()
    report = ET.parse(pytester.path / "results.xml")
    failure = report.find(".//failure")
    assert failure is not None
    assert failure.text is not None
    assert ("RuntimeError: shader input failed" in failure.text) is cause_visible
    assert "shader assertion note" in failure.text
    assert "failure.test.wesl:1:22" in failure.text
    assert "expect failed" in failure.text
