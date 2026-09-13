import subprocess
import sys
from pathlib import Path

subprocess.run(
    [
        "maturin",
        "build",
        "--release",
        "--locked",
        "--auditwheel",
        "skip",
        "--interpreter",
        sys.executable,
        "--out",
        "dist",
    ],
    check=True,
)
(wheel,) = Path("dist").glob("*.whl")
subprocess.run([sys.executable, "-m", "installer", str(wheel)], check=True)
