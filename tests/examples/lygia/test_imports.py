from pathlib import Path

import wesl


def test_upstream_imports(library_directory: Path) -> None:
    directory = Path(__file__).parents[3] / "examples"
    result = wesl.compile_file(
        directory / "lygia/shaders/landscape.wesl",
        root_directory=directory,
        dependencies={"lygia": library_directory},
        options=wesl.CompileOptions(
            features=wesl.Features(flags={"srgb_target": True})
        ),
    )
    assert {
        "lygia::generative::snoise",
        "lygia::math::permute",
    } <= set(result.modules)
    assert "public " not in result.sources["lygia::generative::snoise"].text
