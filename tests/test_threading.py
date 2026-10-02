import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wesl
from wesl import _native


def test_import_preserves_metadata_without_gpu_dependencies() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import wesl; "
                "from importlib.metadata import version; "
                "assert wesl.__version__ == version('wesl-py'); "
                "assert 'wgpu' not in sys.modules; "
                "assert 'pygfx' not in sys.modules"
            ),
        ],
        check=True,
        timeout=30,
    )


def test_concurrent_shader_instrumentation(wgsl_test: Path) -> None:
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
            {"package::main": source},
            "package::main",
            name,
            wesl.TestOptions(),
            {"package::main": filename},
            None,
            0,
            {"wgsl_test": str(wgsl_test)},
            parsed,
        )
        assert compiled is not None
        shader, entry_point, diagnostics, overrides, _ = compiled
        wesl.check_syntax(shader)
        assert entry_point in shader
        assert overrides == {}
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
