import functools
import json
import platform
import statistics
import time

import wesl
from wesl import _native

modules = {
    f"package::module_{index}": f"fn value() -> u32 {{ return {index}u; }}"
    for index in range(64)
}
modules["package::main"] = (
    "\n".join(
        f"import package::module_{index}::value as value_{index};"
        for index in range(64)
    )
    + "\nfn total() -> u32 { return "
    + " + ".join(f"value_{index}()" for index in range(64))
    + "; }"
)
features: dict[str, bool | wesl.Feature] = {"enabled": True}
timings = {}
for name, operation in (
    (
        "facade_compile",
        functools.partial(
            wesl.compile,
            modules,
            options=wesl.CompileOptions(
                strip=False, features=wesl.Features(flags=features)
            ),
        ),
    ),
    (
        "native_boundary_compile",
        functools.partial(
            _native.compile,
            modules,
            root="package::main",
            options=wesl.CompileOptions(
                strip=False, features=wesl.Features(flags=features)
            ),
            mangler=wesl.ManglerKind.Escape.value,
            use_sourcemap=True,
            filenames={},
            root_directory=None,
        ),
    ),
    ("copy_modules_mapping", functools.partial(dict, modules)),
):
    operation()
    samples = []
    for _ in range(7):
        start = time.perf_counter_ns()
        for _ in range(200):
            operation()
        samples.append((time.perf_counter_ns() - start) / 200 / 1000)
    timings[name] = statistics.median(samples)

print(
    json.dumps(
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "binding": wesl.__version__,
            "compiler": wesl.compiler_version,
            "extension": _native.__file__,
            "module_count": len(modules),
            "source_bytes": sum(len(source.encode()) for source in modules.values()),
            "root": "package::main",
            "mangler": "Escape",
            "use_sourcemap": True,
            "options": {
                "features": {"default": "Disable", "flags": features},
                "strip": False,
                "keep_root": False,
                "mangle_root": False,
            },
            "repeats": 7,
            "iterations": 200,
            "median_microseconds": timings,
        },
        indent=2,
    )
)
