import os
from importlib import import_module

import pytest
import wesl

wgpu = pytest.importorskip("wgpu", exc_type=ModuleNotFoundError)
compute_with_buffers = import_module("wgpu.utils.compute").compute_with_buffers


@pytest.mark.gpu
@pytest.mark.parametrize(("enabled", "expected"), [(False, 3), (True, 7)])
def test_compute(modules: dict[str, str], *, enabled: bool, expected: int) -> None:
    try:
        wgpu.gpu.request_adapter_sync()
    except RuntimeError as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(str(error))
    wgsl = wesl.compile(modules, features={"enabled": enabled}).wgsl
    output = compute_with_buffers({}, {0: (1, "I")}, wgsl, n=1)
    assert output[0][0] == expected
