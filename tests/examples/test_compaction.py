# ruff: noqa: PLR2004

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import wgpu

numpy = pytest.importorskip("numpy")
pytest.importorskip("wgpu")
compact = import_module("examples.compaction.compute").compact


@pytest.mark.gpu
@pytest.mark.parametrize(
    ("element_count", "keep_below"),
    [
        pytest.param(0, False, id="empty"),
        pytest.param(129, False, id="block-tail"),
        pytest.param(32769, True, id="multiple-recursive-blocks"),
    ],
)
def test_compaction_preserves_selection_order(
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
@pytest.mark.parametrize("value", [499, 500])
def test_compaction_keeps_all_or_none_for_uniform_input(
    wesl_device: wgpu.GPUDevice, value: int
) -> None:
    values = numpy.full(16385, value, dtype=numpy.uint32)
    output = compact(wesl_device, values)
    expected = values if value >= 500 else numpy.empty(0, dtype=numpy.uint32)
    numpy.testing.assert_array_equal(output, expected)
