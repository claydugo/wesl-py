import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wesl
from wesl import _native


def test_import_preserves_gil_state() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, sysconfig; "
                "import wesl; "
                "assert not sysconfig.get_config_var('Py_GIL_DISABLED') "
                "or not sys._is_gil_enabled()"
            ),
        ],
        env={name: value for name, value in os.environ.items() if name != "PYTHON_GIL"},
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
        [(name, _, _)] = _native.discover_tests(source, filename)
        assert name == f"test_{index}"
        compiled = _native.compile_test(
            {"package::main": source},
            "package::main",
            name,
            wesl.CompileOptions(),
            {"package::main": filename},
            None,
            0,
            {"wgsl_test": str(wgsl_test)},
        )
        assert compiled is not None
        shader, entry_point, diagnostics, overrides = compiled
        wesl.check_syntax(shader)
        assert entry_point in shader
        assert overrides == {}
        [diagnostic] = diagnostics
        return shader, diagnostic

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(compile_test, range(64)))
    for index, (shader, diagnostic) in enumerate(results):
        assert f"test_{index}" in shader
        assert diagnostic.filename == f"shader_{index}.wesl"
        assert diagnostic.message == "expectEq"
        assert diagnostic.source is not None
        assert f"expectEq({index}u, {index}u)" in diagnostic.source
