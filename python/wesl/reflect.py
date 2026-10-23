from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from . import _native

if TYPE_CHECKING:
    from collections.abc import Buffer

    import numpy as np

    from . import Compiler

__all__ = [
    "EntryPoint",
    "TypeShapeError",
    "VarReflection",
    "build_struct_registry",
    "classify_entry_points",
    "decode_buffer",
    "numpy_dtype",
    "var_reflection",
]


type _Layout = str | tuple[Any, ...]
type _Decoded = np.ndarray | dict[str, _Decoded]


class TypeShapeError(ValueError):
    def __init__(self, message: str, var_name: str | None = None) -> None:
        super().__init__(message)
        self.var_name = var_name


@dataclass(frozen=True)
class VarReflection:
    var_name: str
    address_space: str | None
    access_mode: str | None
    group: int | None
    binding: int | None
    dtype: np.dtype[Any] | None
    byte_size: int


class EntryPoint(NamedTuple):
    fn_name: str
    stage: str
    workgroup_size: tuple[int, int, int] | None


def _array_dtype(layout: _Layout) -> np.dtype[Any]:
    import numpy as np

    if isinstance(layout, str):
        return np.dtype(
            {"f16": "<f2", "f32": "<f4", "i32": "<i4", "u32": "<u4"}[layout]
        )
    if layout[0] == "struct":
        _, members, size = layout
        return np.dtype(
            {
                "names": [name for name, _, _ in members],
                "formats": [_array_dtype(member) for _, _, member in members],
                "offsets": [offset for _, offset, _ in members],
                "itemsize": size,
            }
        )
    _, element, count, stride = layout
    element_dtype = _array_dtype(element)
    if element_dtype.itemsize < stride:
        base, shape = cast(
            "tuple[np.dtype[Any], tuple[int, ...]]", element_dtype.subdtype
        )
        element_dtype = np.dtype((base, (*shape[:-1], stride // base.itemsize)))
    if count is None:
        return element_dtype
    return np.dtype((element_dtype, (count,)))


def _decode(
    layout: _Layout,
    data: bytearray,
    size: int,
    *,
    offset: int = 0,
    shape: tuple[int, ...] = (),
    strides: tuple[int, ...] = (),
) -> _Decoded:
    import numpy as np

    while not isinstance(layout, str) and layout[0] == "array":
        _, layout, count, stride = layout
        shape = (*shape, size // stride if count is None else count)
        strides = (*strides, stride)
    if isinstance(layout, str):
        return np.ndarray(
            shape, _array_dtype(layout), buffer=data, offset=offset, strides=strides
        )
    _, members, _ = layout
    return {
        name: _decode(
            member,
            data,
            size,
            offset=offset + member_offset,
            shape=shape,
            strides=strides,
        )
        for name, member_offset, member in members
    }


def numpy_dtype(compiler: Compiler, path: str) -> np.dtype[Any]:
    variable, layout = _native.path_layout(compiler, path)
    return _array_dtype(layout if variable else layout[1])


def decode_buffer(
    compiler: Compiler, path: str, data: Buffer, *, offset: int = 0
) -> _Decoded:
    _, layout = _native.path_layout(compiler, path)
    data = bytearray(data)
    return _decode(layout, data, len(data) - offset, offset=offset)


def var_reflection(compiler: Compiler, path: str) -> VarReflection:
    address_space, access_mode, group, binding, layout, byte_size = (
        _native.var_reflection(compiler, path)
    )
    return VarReflection(
        var_name=path.rpartition("::")[2],
        address_space=address_space,
        access_mode=access_mode,
        group=group,
        binding=binding,
        dtype=None if layout is None else _array_dtype(layout),
        byte_size=byte_size,
    )


def build_struct_registry(
    compiler: Compiler, module: str
) -> dict[str, np.dtype[Any] | None]:
    return {
        name: None if layout is None else _array_dtype(layout)
        for name, layout in _native.struct_layouts(compiler, module)
    }


def classify_entry_points(compiler: Compiler, module: str) -> list[EntryPoint]:
    return [
        EntryPoint(fn_name, stage, workgroup_size)
        for fn_name, stage, workgroup_size in _native.entry_points(compiler, module)
    ]
