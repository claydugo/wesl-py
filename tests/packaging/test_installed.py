import hashlib
import json
import os
import sys
import sysconfig
from email import message_from_string
from importlib import import_module
from importlib.metadata import distribution
from importlib.util import find_spec
from pathlib import Path

import pytest


def test_installed(pytestconfig: pytest.Config) -> None:
    path = pytestconfig.getoption("--installation")
    if path is None:
        pytest.skip("requires an artifact installation")
    installation = json.loads(path.read_text())
    assert sys.version_info[:2] == tuple(map(int, installation["python"].split(".")))
    assert (
        bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
        == installation["freethreading"]
    )
    if installation["freethreading"]:
        assert "PYTHON_GIL" not in os.environ
        assert not sys._is_gil_enabled()  # noqa: SLF001
    wesl = import_module("wesl")
    if installation["freethreading"]:
        assert not sys._is_gil_enabled()  # noqa: SLF001
    package = distribution("wesl-py")
    assert wesl.__version__ == package.version == installation["version"]
    assert Path(wesl.__file__).is_relative_to(sys.prefix)
    assert Path(wesl.__file__).with_name("py.typed").is_file()
    assert Path(wesl.__file__).with_name("_native.pyi").is_file()
    assert "wgpu" not in sys.modules
    shader = wesl.compile_source("@compute @workgroup_size(1) fn main() {}")
    assert "fn main(" in shader.wgsl
    if installation["kind"] == "wheel":
        native = import_module("wesl._native")
        assert Path(native.__file__).is_relative_to(sys.prefix)
        assert (
            hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
            == installation["extension_hash"]
        )
        metadata = message_from_string(package.read_text("WHEEL"))
        assert set(metadata.get_all("Tag")) == set(installation["tags"])
        if installation["extra"] is None:
            assert find_spec("wgpu") is None
        assert not list((Path(sys.prefix) / "conda-meta").glob("rust-*.json"))
    else:
        assert find_spec("maturin") is None
    if installation["extra"] == "examples":
        for module in (
            "imageio",
            "numpy",
            "wgpu",
            "imgui_bundle",
            "glfw",
            "pygfx",
            "rendercanvas",
            "tifffile",
        ):
            import_module(module)
    if installation["compute"]:
        wgpu = import_module("wgpu")
        adapter = wgpu.gpu.request_adapter_sync()
        assert adapter.info["adapter_type"] == "CPU"
        assert adapter.info["backend_type"] == "Vulkan"
