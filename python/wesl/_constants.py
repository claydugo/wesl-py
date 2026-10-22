import math
import operator
from collections.abc import Mapping
from numbers import Integral, Real
from typing import SupportsFloat

from ._native import constant_module


def _normalize_constant(
    value: SupportsFloat | str, *, module: str, name: str
) -> bool | int | float | str:
    if isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, Integral)):
        try:
            integer = operator.index(value)
        except TypeError as error:
            message = f"{module}::{name}: expected an integer"
            raise TypeError(message) from error
        if not -(2**63) <= integer < 2**63:
            message = f"{module}::{name}: integer is outside the signed 64-bit range"
            raise ValueError(message)
        return integer
    if isinstance(value, (float, Real)):
        try:
            number = float(value)
        except OverflowError as error:
            message = f"{module}::{name}: value is outside the finite float range"
            raise ValueError(message) from error
        if not math.isfinite(number):
            message = f"{module}::{name}: value must be finite"
            raise ValueError(message)
        if number != value:
            message = f"{module}::{name}: conversion to float loses precision"
            raise ValueError(message)
        return number
    message = (
        f"{module}::{name}: expected bool, int, real scalar, or str;"
        f" got {type(value).__name__}"
    )
    raise TypeError(message)


def add_constant_modules(
    modules: Mapping[str, str],
    constant_modules: Mapping[str, Mapping[str, SupportsFloat | str]],
) -> dict[str, str]:
    if not isinstance(constant_modules, Mapping):
        message = "constants must be a mapping or None"
        raise TypeError(message)
    modules = dict(modules)
    for module, constants in constant_modules.items():
        if not isinstance(module, str):
            message = "constant module names must be strings"
            raise TypeError(message)
        if module in modules:
            message = (
                f"{module!r} is in modules and also comes from the constants argument."
                " Pass the values in one place. In pytest, the wesl_constants"
                " fixture adds the module to wesl_compiler.modules."
            )
            raise ValueError(message)
        if not isinstance(constants, Mapping):
            message = f"{module!r}: constants must be a mapping"
            raise TypeError(message)
        normalized = {}
        for name, value in constants.items():
            if not isinstance(name, str):
                message = f"{module!r}: constant names must be strings"
                raise TypeError(message)
            normalized[name] = _normalize_constant(value, module=module, name=name)
        modules[module] = constant_module(module, normalized)
    return modules
