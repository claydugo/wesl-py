# ruff: noqa: PLR2004

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    import wesl
    import wgpu

numpy = pytest.importorskip("numpy")
pytest.importorskip("wgpu")
compute_with_buffers = import_module("wgpu.utils.compute").compute_with_buffers
compact = import_module("examples.compaction.compute").compact


@pytest.mark.gpu
@pytest.mark.parametrize("element_count", [1, 127, 128, 129, 16385])
def test_scan(wesl_compiler: wesl.Compiler, element_count: int) -> None:
    wesl_compiler.options.features.flags = {"select_values": False, "keep_below": False}
    values = numpy.random.default_rng(3).integers(
        0, 1000, element_count, dtype=numpy.uint32
    )
    output = compute_with_buffers(
        {
            0: values,
            1: numpy.full_like(values, 0xFFFFFFFF),
            2: numpy.full((element_count + 127) // 128, 0xFFFFFFFF, dtype=numpy.uint32),
        },
        {1: (element_count, "I"), 2: ((element_count + 127) // 128, "I")},
        wesl_compiler.compile_file("examples/compaction/shaders/scan.wesl").wgsl,
        n=(element_count + 127) // 128,
    )
    expected = numpy.empty_like(values)
    totals = []
    for start in range(0, element_count, 128):
        block = values[start : start + 128].astype(numpy.uint64)
        expected[start : start + 128] = numpy.cumsum(block) - block
        totals.append(block.sum())
    numpy.testing.assert_array_equal(output[1], expected)
    numpy.testing.assert_array_equal(output[2], totals)


@pytest.mark.gpu
@pytest.mark.parametrize("keep_below", [False, True])
@pytest.mark.parametrize("element_count", [0, 1, 127, 128, 129, 16384, 16385, 32769])
def test_compact(
    wesl_device: wgpu.GPUDevice, element_count: int, *, keep_below: bool
) -> None:
    values = (numpy.arange(element_count, dtype=numpy.uint64) * 2654435761).astype(
        numpy.uint32
    )
    output = compact(wesl_device, values, threshold=2**31, keep_below=keep_below)
    expected = values[values < 2**31] if keep_below else values[values >= 2**31]
    assert output.dtype == numpy.uint32
    numpy.testing.assert_array_equal(output, expected)


@pytest.mark.gpu
@pytest.mark.parametrize("threshold", [0, 500, 0xFFFFFFFF])
@pytest.mark.parametrize("keep_below", [False, True])
def test_threshold(
    wesl_device: wgpu.GPUDevice, threshold: int, *, keep_below: bool
) -> None:
    values = numpy.tile(
        numpy.array([0, 499, 500, 501, 0xFFFFFFFF], dtype=numpy.uint32), 27
    )[::-1]
    output = compact(wesl_device, values, threshold=threshold, keep_below=keep_below)
    expected = values[values < threshold] if keep_below else values[values >= threshold]
    numpy.testing.assert_array_equal(output, expected)


@pytest.mark.gpu
@pytest.mark.parametrize("value", [499, 500])
@pytest.mark.parametrize("keep_below", [False, True])
def test_uniform(wesl_device: wgpu.GPUDevice, value: int, *, keep_below: bool) -> None:
    values = numpy.full(16385, value, dtype=numpy.uint32)
    output = compact(wesl_device, values, keep_below=keep_below)
    expected = (
        values if (value < 500) == keep_below else numpy.empty(0, dtype=numpy.uint32)
    )
    numpy.testing.assert_array_equal(output, expected)


@pytest.mark.parametrize(
    "values",
    [numpy.zeros((1, 2), dtype=numpy.uint32), numpy.array([-1], dtype=numpy.int32)],
)
def test_invalid_inputs(values: numpy.ndarray) -> None:
    with pytest.raises(ValueError, match="one-dimensional uint32 array"):
        compact(cast("wgpu.GPUDevice", None), values)
