import pytest
import wesl


def test_imported_feature(wesl_compiler: wesl.Compiler) -> None:
    shader = wesl_compiler.compile_source("""
        import package::tests::examples::testing::shaders::levels::adjust;
        @compute @workgroup_size(1)
        fn main() { let value = adjust(0.75); }
    """)
    assert "package::tests::examples::testing::shaders::levels" in shader.modules
    assert ("clamp(" in shader.wgsl) == wesl_compiler.options.features.flags["clamped"]


def test_invalid_shader() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_source(
            "@compute @workgroup_size(1) fn main() { let value = ; }",
            filename="invalid.wesl",
        )
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.filename == "invalid.wesl"
    assert diagnostic.line == 1
    assert "unexpected" in diagnostic.message
