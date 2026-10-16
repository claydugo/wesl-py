from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import wgpu

np = pytest.importorskip("numpy")
pytest.importorskip("wgpu")
Compactor = import_module("examples.compaction.compute").Compactor


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
    values = (np.arange(element_count, dtype=np.uint64) * 2654435761).astype(np.uint32)
    compactor = Compactor(wesl_device, threshold=2**31, keep_below=keep_below)
    output = compactor.compact(values)
    expected = values[values < 2**31] if keep_below else values[values >= 2**31]
    assert output.dtype == np.uint32
    np.testing.assert_array_equal(output, expected)


@pytest.mark.gpu
@pytest.mark.parametrize("value", [499, 500])
def test_compaction_keeps_all_or_none_for_uniform_input(
    wesl_device: wgpu.GPUDevice, value: int
) -> None:
    values = np.full(16385, value, dtype=np.uint32)
    compactor = Compactor(wesl_device)
    output = compactor.compact(values)
    expected = values if value >= 500 else np.empty(0, dtype=np.uint32)
    np.testing.assert_array_equal(output, expected)


@pytest.mark.gpu
def test_prepared_compaction_accepts_new_inputs(
    wesl_device: wgpu.GPUDevice,
) -> None:
    compactor = Compactor(wesl_device)
    for element_count, offset in ((129, 0), (32769, 0), (0, 0), (1025, 0), (129, 500)):
        values = np.arange(element_count, dtype=np.uint32) + offset
        np.testing.assert_array_equal(compactor.compact(values), values[values >= 500])
