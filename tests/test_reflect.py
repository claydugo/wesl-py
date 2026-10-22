from __future__ import annotations

import pytest
import wesl
from wesl.reflect import (
    EntryPoint,
    TypeShapeError,
    VarReflection,
    build_struct_registry,
    classify_entry_points,
    decode_buffer,
    numpy_dtype,
    var_reflection,
)


def test_reflection_reads_module_declarations() -> None:
    np = pytest.importorskip("numpy")
    compiler = wesl.Compiler(
        modules={
            "package::shapes": "struct Imported { value: f32 }",
            "package::broken": "@compute @workgroup_size(missing) fn main() {}",
            "package::main": """
                import package::shapes::Imported;
                const base = 2u;
                override lanes: u32 = 8u;
                const unsupported = quantizeToF16(1.5);
                struct Particle { position: vec3f, @align(16) mass: f32 }
                struct Tail { count: u32, values: array<f32> }
                @group(base - 1u) @binding(base * 2u) var<uniform> settings: Particle;
                @group(0) @binding(0)
                var<storage, read_write> particles: array<Particle>;
                @group(0) @binding(1) var<storage> tail: Tail;
                @group(0) @binding(2) var<storage> points: array<vec3f>;
                @group(0) @binding(3) var image: texture_2d<f32>;
                var<workgroup> scratch: array<Imported, 4>;
                var<workgroup> tile: array<f32, lanes>;
                @compute @workgroup_size(base * 4u, 2) fn sized() {}
                @compute @workgroup_size(lanes) fn overridden() {}
                @vertex fn draw() -> @builtin(position) vec4f { return vec4f(); }
                @fragment fn shade() -> @location(0) vec4f { return vec4f(); }
                fn helper() {}
            """,
        }
    )
    particle = numpy_dtype(compiler, "package::main::Particle")
    assert [
        var_reflection(compiler, f"package::main::{name}")
        for name in ("settings", "particles", "tail", "points", "scratch", "tile")
    ] == [
        VarReflection("settings", "uniform", None, 1, 4, particle, 32),
        VarReflection("particles", "storage", "read_write", 0, 0, particle, 0),
        VarReflection("tail", "storage", None, 0, 1, None, 0),
        VarReflection("points", "storage", None, 0, 2, np.dtype(("<f4", (4,))), 0),
        VarReflection(
            "scratch",
            "workgroup",
            None,
            None,
            None,
            np.dtype((numpy_dtype(compiler, "package::shapes::Imported"), (4,))),
            16,
        ),
        VarReflection("tile", "workgroup", None, None, None, None, 0),
    ]
    assert numpy_dtype(compiler, "package::main::settings") == particle
    assert numpy_dtype(compiler, "package::main::points") == np.dtype(("<f4", (4,)))
    points = np.arange(8, dtype="<f4").tobytes()
    decoded = decode_buffer(
        compiler, "package::main::points", bytes(8) + points, offset=8
    )
    np.testing.assert_array_equal(decoded, [[0, 1, 2], [4, 5, 6]])
    settings = np.zeros((), particle)
    settings["mass"] = 2.5
    decoded = decode_buffer(compiler, "package::main::settings", settings.tobytes())
    assert (decoded["position"].shape, decoded["mass"].shape) == ((3,), ())
    np.testing.assert_array_equal(decoded["mass"], 2.5)
    for path, var_name in [
        ("package::main::image", "image"),
        ("package::main::missing", "missing"),
    ]:
        with pytest.raises(TypeShapeError) as error:
            numpy_dtype(compiler, path)
        assert error.value.var_name == var_name
    with pytest.raises(TypeShapeError, match="texture or sampler"):
        var_reflection(compiler, "package::main::image")
    assert build_struct_registry(compiler, "package::main") == {
        "Particle": particle,
        "Tail": None,
    }
    assert classify_entry_points(compiler, "package::main") == [
        EntryPoint("sized", "compute", (8, 2, 1)),
        EntryPoint("overridden", "compute", None),
        EntryPoint("draw", "vertex", None),
        EntryPoint("shade", "fragment", None),
    ]
    with pytest.raises(wesl.CompileError, match="in package::broken"):
        classify_entry_points(compiler, "package::broken")
