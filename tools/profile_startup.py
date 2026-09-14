import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repeats", type=int, default=15)
arguments = parser.parse_args()
if arguments.repeats < 1:
    parser.error("--repeats must be positive")
manifest = str(Path(__file__).resolve().parents[1] / "pixi.toml")
pixi = shutil.which("pixi")
if pixi is None:
    parser.error("pixi is required")
timings = {}
for name, command in (
    ("python_process", [sys.executable, "-c", "pass"]),
    ("python_import_wesl", [sys.executable, "-c", "import wesl"]),
    (
        "pixi_run_import_wesl",
        [pixi, "run", "--manifest-path", manifest, "python", "-c", "import wesl"],
    ),
    (
        "pixi_as_is_import_wesl",
        [
            pixi,
            "run",
            "--as-is",
            "--manifest-path",
            manifest,
            "python",
            "-c",
            "import wesl",
        ],
    ),
):
    samples = []
    for _ in range(arguments.repeats):
        start = time.perf_counter_ns()
        subprocess.run(command, check=True, capture_output=True)
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    timings[name] = {
        "median": statistics.median(samples),
        "minimum": min(samples),
        "maximum": max(samples),
    }

samples = [
    json.loads(
        subprocess.check_output(
            [
                sys.executable,
                "-c",
                (
                    "import time; start = time.perf_counter_ns(); import wesl; "
                    "import_time = (time.perf_counter_ns() - start) / 1_000_000; "
                    "start = time.perf_counter_ns(); "
                    "wesl.compile({'package::main': 'fn main() {}'}, "
                    "options=wesl.CompileOptions(strip=False)); "
                    "compile_time = (time.perf_counter_ns() - start) / 1_000_000; "
                    "import json; print(json.dumps([import_time, compile_time]))"
                ),
            ],
            text=True,
        ),
    )
    for _ in range(arguments.repeats)
]
print(
    json.dumps(
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "executable": sys.executable,
            "repeats": arguments.repeats,
            "process_milliseconds": timings,
            "import_median_milliseconds": statistics.median(
                sample[0] for sample in samples
            ),
            "first_compile_median_milliseconds": statistics.median(
                sample[1] for sample in samples
            ),
            "first_compile_source": "fn main() {}",
        },
        indent=2,
    ),
)
