import math
import operator
from collections.abc import Mapping
from numbers import Integral, Real
from typing import SupportsFloat

from ._native import constant_module


def _normalize_constant(
    value: SupportsFloat, *, module: str, name: str
) -> bool | int | float:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, Integral)):
        try:
            integer = operator.index(value)
        except TypeError as error:
            raise TypeError(f"{module}::{name}: expected an integer") from error
        if not -(2**63) <= integer < 2**63:
            raise ValueError(
                f"{module}::{name}: integer is outside the signed 64-bit range"
            )
        return integer
    if isinstance(value, (float, Real)):
        try:
            number = float(value)
        except OverflowError as error:
            raise ValueError(
                f"{module}::{name}: value is outside the finite float range"
            ) from error
        if not math.isfinite(number):
            raise ValueError(f"{module}::{name}: value must be finite")
        if number != value:
            raise ValueError(f"{module}::{name}: conversion to float loses precision")
        return number
    raise TypeError(
        f"{module}::{name}: expected bool, int, or real scalar;"
        f" got {type(value).__name__}"
    )


def add_constant_modules(
    modules: Mapping[str, str],
    constant_modules: Mapping[str, Mapping[str, SupportsFloat]],
) -> dict[str, str]:
    if not isinstance(constant_modules, Mapping):
        raise TypeError("constant_modules must be a mapping or None")
    modules = dict(modules)
    for module, constants in constant_modules.items():
        if not isinstance(module, str):
            raise TypeError("constant module names must be strings")
        if module in modules:
            raise ValueError(
                f"{module!r} is present in both modules and constant_modules"
            )
        if not isinstance(constants, Mapping):
            raise TypeError(f"{module!r}: constants must be a mapping")
        normalized = {}
        for name, value in constants.items():
            if not isinstance(name, str):
                raise TypeError(f"{module!r}: constant names must be strings")
            normalized[name] = _normalize_constant(value, module=module, name=name)
        modules[module] = constant_module(module, normalized)
    return modules
