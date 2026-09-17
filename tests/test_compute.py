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
    wgsl = wesl.compile(
        modules,
        options=wesl.CompileOptions(features=wesl.Features(flags={"enabled": enabled})),
    ).wgsl
    output = compute_with_buffers({}, {0: (1, "I")}, wgsl, n=1)
    assert output[0][0] == expected


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("constants", "expected"),
    [
        ("const result: f32 = 1;", 1065353216),
        ("const result = base + 1u; const base = 2u;", 3),
    ],
)
@pytest.mark.parametrize(
    "lower",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.xfail(
                strict=True,
                raises=(AssertionError, wgpu.GPUValidationError),
                reason="constant lowering does not preserve these expressions",
            ),
        ),
    ],
)
def test_constant_semantics(constants: str, expected: int, *, lower: bool) -> None:
    try:
        wgpu.gpu.request_adapter_sync()
    except RuntimeError as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(str(error))
    result = wesl.compile_source(
        f"""
        {constants}
        @group(0) @binding(0) var<storage, read_write> output: array<u32>;
        @compute @workgroup_size(1) fn main() {{ output[0] = bitcast<u32>(result); }}
        """,
        options=wesl.CompileOptions(lower=lower),
    )
    output = compute_with_buffers({}, {0: (1, "I")}, result.wgsl, n=1)
    assert output[0][0] == expected
