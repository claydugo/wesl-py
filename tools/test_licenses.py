import subprocess
from pathlib import Path

import yaml

bundle = yaml.safe_load(Path("THIRDPARTY.yml").read_text())
for package in bundle["third_party_libraries"]:
    assert package["licenses"], package["package_name"]
    for license_entry in package["licenses"]:
        assert license_entry["text"].strip(), package["package_name"]

Path("target").mkdir(exist_ok=True)
subprocess.run(
    [
        "cargo",
        "bundle-licenses",
        "--format",
        "yaml",
        "--prefer",
        "MIT",
        "--previous",
        "THIRDPARTY.yml",
        "--check-previous",
        "--output",
        "target/THIRDPARTY.yml",
    ],
    check=True,
)
