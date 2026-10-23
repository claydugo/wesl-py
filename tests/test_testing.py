from __future__ import annotations

import itertools
from struct import pack, unpack
from typing import TYPE_CHECKING

import pytest
import wesl
from wesl.reflect import decode_buffer, numpy_dtype
from wesl.testing import (
    ShaderAssertionError,
    run_compute,
    run_test,
    run_test_cpu,
)

if TYPE_CHECKING:
    from functools import partial
    from pathlib import Path

    import wgpu


def test_shader_test_visibility(shader_runner: partial) -> None:
    modules = {
        "package::main": (
            "import library::value; import wgsl_test::expectEq; "
            "@test fn selected() { expectEq(value(), 7u); }"
        ),
        "library": "fn value() -> u32 { return 7u; }",
    }
    shader_runner(wesl.Compiler(modules=modules), "selected")
    options = wesl.TestOptions(visibility=True)
    with pytest.raises(wesl.CompileError, match="visibility"):
        shader_runner(wesl.Compiler(modules=modules), "selected", options=options)
    modules["library"] = "public fn value() -> u32 { return 7u; }"
    shader_runner(wesl.Compiler(modules=modules), "selected", options=options)


@pytest.mark.parametrize(
    "override", [False, True], ids=["filesystem", "virtual-override"]
)
def test_run_test_uses_explicit_dependencies(
    shader_runner: partial, tmp_path: Path, *, override: bool
) -> None:
    common = tmp_path / "common"
    common.mkdir()
    (common / "package.wesl").write_text(
        "var<private> counter: u32 = 0u; "
        "fn next() -> u32 { counter += 1u; return counter; }"
    )
    expected = 11 if override else 1
    modules = {
        "package::main": "@test fn selected() { "
        f"wgsl_test::expectEq(common::next(), {expected}u); "
        f"wgsl_test::expectEq(common::next(), {expected + 1}u); }}"
    }
    if override:
        modules["common"] = (
            "var<private> counter: u32 = 10u; "
            "fn next() -> u32 { counter += 1u; return counter; }"
        )
    shader_runner(
        wesl.Compiler(modules=modules, dependencies={"common": common}),
        "selected",
    )


@pytest.mark.gpu
def test_run_test_resources(wesl_device: wgpu.GPUDevice) -> None:
    import wgpu

    texture = wesl_device.create_texture(
        size=(1, 1, 1),
        format="rgba8unorm",
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    buffers = [
        wesl_device.create_buffer_with_data(
            data=pack("<4I", increment, 0, 0, 0), usage=wgpu.BufferUsage.UNIFORM
        )
        for increment in (3, 0)
    ] + [
        wesl_device.create_buffer_with_data(
            data=bytes(256) + pack("<I", initial),
            usage=wgpu.BufferUsage.STORAGE
            | wgpu.BufferUsage.COPY_SRC
            | wgpu.BufferUsage.COPY_DST,
        )
        for initial in (4, 10)
    ]
    try:
        wesl_device.queue.write_texture(
            {"texture": texture},
            bytes((255, 0, 0, 255)),
            {"bytes_per_row": 4},
            (1, 1, 1),
        )

        def bindings(
            increment: wgpu.GPUBuffer, value: wgpu.GPUBuffer
        ) -> dict[int, list[dict[str, object]]]:
            return {
                0: [{"binding": 0, "resource": {"buffer": increment}}],
                2: [
                    {"binding": 0, "resource": texture.create_view()},
                    {
                        "binding": 1,
                        "resource": {"buffer": value, "offset": 256, "size": 4},
                    },
                    {"binding": 2, "resource": wesl_device.create_sampler()},
                ],
            }

        resources = bindings(buffers[0], buffers[2])
        modules = {
            "package::main": """
                @group(0) @binding(0) var<uniform> increment: vec4u;
                @group(2) @binding(0) var image: texture_2d<f32>;
                @group(2) @binding(1) var<storage, read_write> value: u32;
                @group(2) @binding(2) var linear: sampler;
                @test fn accumulate() {
                    value += increment.x;
                    wgsl_test::expectEq(value, constants::expected);
                    wgsl_test::expectNearVec4(
                        textureSampleLevel(image, linear, vec2f(0.5), 0.0),
                        vec4f(1.0, 0.0, 0.0, 1.0),
                    );
                }
            """
        }
        compiler = wesl.Compiler(modules=modules)
        run_test(
            wesl_device,
            compiler,
            "accumulate",
            resources=resources,
            constants={"expected": 7},
        )
        run_test(
            wesl_device,
            compiler,
            "accumulate",
            resources=resources,
            constants={"expected": 10},
        )
        with pytest.raises(ShaderAssertionError) as failure:
            run_test(
                wesl_device,
                compiler,
                "accumulate",
                resources=resources,
                constants={"expected": 10},
            )
        assert (failure.value.checks, failure.value.failures) == (2, 1)
        run_test(
            wesl_device,
            compiler,
            "accumulate",
            resources=bindings(buffers[1], buffers[3]),
            constants={"expected": 10},
        )
        wesl_device.queue.write_buffer(buffers[2], 256, pack("<I", 7))
        run_test(
            wesl_device,
            compiler,
            "accumulate",
            resources=resources,
            constants={"expected": 10},
        )
        assert unpack(
            "<I", wesl_device.queue.read_buffer(buffers[2], buffer_offset=256, size=4)
        ) == (10,)
        assert [len(entries) for entries in resources.values()] == [1, 3]
    finally:
        texture.destroy()
        for buffer in buffers:
            buffer.destroy()


@pytest.mark.gpu
def test_float32_texture_layouts(wesl_device: wgpu.GPUDevice) -> None:
    import wgpu

    assert "float32-filterable" not in wesl_device.features
    texture = wesl_device.create_texture(
        size=(1, 1, 1),
        format="r32float",
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    try:
        wesl_device.queue.write_texture(
            {"texture": texture},
            pack("<f", 1.0000009536743164),
            {"bytes_per_row": 4},
            (1, 1, 1),
        )
        resources = {
            0: [
                {"binding": 0, "resource": texture.create_view()},
                {
                    "binding": 1,
                    "resource": wesl_device.create_sampler(
                        mag_filter="nearest", min_filter="nearest"
                    ),
                },
            ]
        }
        layouts = {
            0: [
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "texture": {"sample_type": "unfilterable-float"},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "sampler": {"type": "non-filtering"},
                },
            ]
        }
        run_test(
            wesl_device,
            wesl.Compiler(
                modules={
                    "package::main": """
                    @group(0) @binding(0) var image: texture_2d<f32>;
                    @group(0) @binding(1) var nearest: sampler;
                    @test fn sample() {
                        wgsl_test::expectUlp(
                            textureSampleLevel(image, nearest, vec2f(0.5), 0.0).x,
                            1.0000009536743164,
                            0u,
                        );
                    }
                """
                }
            ),
            "sample",
            resources=resources,
            layouts=layouts,
        )
        assert [len(entries) for entries in resources.values()] == [2]
        assert [len(entries) for entries in layouts.values()] == [2]
    finally:
        texture.destroy()


@pytest.mark.gpu
def test_buffer_variables_get_zeroed_storage(wesl_device: wgpu.GPUDevice) -> None:
    import wgpu

    values = wesl_device.create_buffer_with_data(
        data=pack("<2I", 3, 4), usage=wgpu.BufferUsage.STORAGE
    )
    source = """
        @group(0) @binding(1) var<storage, read> values: array<u32, 2>;
        @buffer var<storage, read_write> scratch: array<u32, 4>;
        @buffer var<storage, read_write> unused: array<u32, 4>;
        @test fn scratch_starts_at_zero() {
            wgsl_test::expectEq(scratch[3], 0u);
            scratch[3] = values[1];
            wgsl_test::expectEq(scratch[3], 4u);
        }
        @test fn uses_no_resource() { wgsl_test::expectEq(3u, 3u); }
    """
    try:
        for strip, test_name in itertools.product(
            [True, False], ["scratch_starts_at_zero", "uses_no_resource"]
        ):
            run_test(
                wesl_device,
                wesl.Compiler(modules={"package::main": source}),
                test_name,
                options=wesl.TestOptions(strip=strip),
                resources={
                    0: [{"binding": 1, "resource": {"buffer": values}}],
                    1: [{"binding": 0, "resource": {"buffer": values}}],
                },
            )
    finally:
        values.destroy()
    run_test(
        wesl_device,
        wesl.Compiler(
            modules={
                "package::main": "@buffer var<storage, read> zeros: array<u32, 4>; "
                "@test fn reads() { wgsl_test::expectEq(zeros[3], 0u); }"
            }
        ),
        "reads",
        layouts={},
    )
    with pytest.raises(ValueError, match="must be a var<storage>"):
        run_test(
            wesl_device,
            wesl.Compiler(
                modules={
                    "package::main": "@buffer var<uniform> scale: vec4f; "
                    "@test fn reads() { wgsl_test::expectNear(scale.x, 0.0); }"
                }
            ),
            "reads",
        )


@pytest.mark.gpu
def test_run_compute_returns_buffers_by_name(wesl_device: wgpu.GPUDevice) -> None:
    import wgpu

    np = pytest.importorskip("numpy")
    results = run_compute(
        wesl_device,
        wesl.Compiler(),
        """
            @buffer var<storage, read_write> squares: array<u32, 8>;
            @buffer var<storage> offsets: array<f32, 1>;
            @buffer var<storage, read_write> halves: array<f32, 4>;
            @buffer var<storage, read_write> unused: array<f32, 2>;
            @compute @workgroup_size(4)
            fn main(@builtin(global_invocation_id) index: vec3u) {
                squares[index.x] = index.x * index.x + constants::shift;
                if index.x < 2u {
                    halves[index.x] =
                        f32(index.x) * constants::scale + offsets[0] + 999.0;
                }
            }
        """,
        constants={"shift": 1, "scale": 0.5},
        dispatch_workgroups=2,
    )
    assert list(results) == ["squares", "halves", "unused"]
    np.testing.assert_array_equal(results["squares"], np.arange(8) ** 2 + 1)
    np.testing.assert_array_equal(results["halves"], [0.0, 0.5, -999.0, -999.0])
    np.testing.assert_array_equal(results["unused"], [-999.0, -999.0])
    assert results["halves"].dtype == np.float32
    compiler = wesl.Compiler(
        modules={"package::shapes": "struct Pair { count: u32, turn: mat3x3f }"}
    )
    source = """
        import package::shapes::Pair;
        @buffer var<storage, read> values: array<i32>;
        @buffer var<storage, read_write> points: array<vec3i, 2>;
        @buffer var<storage, read_write> turn: mat3x3f;
        @buffer var<storage, read_write> pairs: array<Pair, 2>;
        @compute @workgroup_size(1) fn main() {
            let last = arrayLength(&values) - 1u;
            points[1] = vec3i(values[0], values[1], values[last]);
            turn = mat3x3f(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0);
            pairs[0] = Pair(arrayLength(&values), turn);
        }
    """
    shaped = run_compute(
        wesl_device,
        compiler,
        source,
        buffers={
            "values": [-3, 4, 0, 9],
            "pairs": {"count": [0, 9], "turn": np.zeros((2, 3, 3))},
        },
    )
    assert shaped["points"].shape == (2, 3)
    np.testing.assert_array_equal(shaped["points"][1], [-3, 4, 9])
    np.testing.assert_array_equal(shaped["turn"], np.arange(1, 10).reshape(3, 3))
    np.testing.assert_array_equal(shaped["pairs"]["count"], [4, 9])
    np.testing.assert_array_equal(
        shaped["pairs"]["turn"][0], np.arange(1, 10).reshape(3, 3)
    )
    raw = np.zeros(2, numpy_dtype(compiler, "package::shapes::Pair"))
    assert (raw.itemsize, raw["turn"].shape) == (64, (2, 3, 4))
    raw["count"] = [5, 6]
    raw["turn"][1, :, :3] = np.arange(9).reshape(3, 3)
    decoded = decode_buffer(compiler, "package::shapes::Pair", raw.tobytes())
    np.testing.assert_array_equal(decoded["count"], [5, 6])
    np.testing.assert_array_equal(decoded["turn"][1], np.arange(9).reshape(3, 3))
    with pytest.raises(ValueError, match="no @buffer variable is named missing"):
        run_compute(wesl_device, compiler, source, buffers={"missing": [1]})
    with pytest.raises(ValueError, match="requires a @buffer"):
        run_compute(
            wesl_device,
            wesl.Compiler(),
            "@compute @workgroup_size(1) fn main() {}",
        )
    with pytest.raises(wgpu.GPUValidationError):
        run_compute(
            wesl_device,
            wesl.Compiler(
                modules={
                    "package::main": "import package::util::fill; "
                    "@buffer var<storage, read_write> values: array<u32, 1>; "
                    "@compute @workgroup_size(1) fn main() { values[0] = fill(); }",
                    "package::util": "@buffer var<storage, read_write> "
                    "values: array<u32, 1>; "
                    "fn fill() -> u32 { values[0] = 7u; return values[0]; }",
                }
            ),
        )


@pytest.mark.gpu
def test_shader_errors_name_source_declarations(wesl_device: wgpu.GPUDevice) -> None:
    import wgpu

    compiler = wesl.Compiler(
        modules={
            "package::util": "fn fill() -> u32 { let value: f32 = 1.5; return value; }"
        }
    )
    with pytest.raises(wgpu.GPUValidationError, match="'package::util::fill'") as error:
        run_compute(
            wesl_device,
            compiler,
            "import package::util::fill; "
            "@buffer var<storage, read_write> values: array<u32, 1>; "
            "@compute @workgroup_size(1) fn main() { values[0] = fill(); }",
        )
    assert not any(
        "package::util::fill" in line
        for line in str(error.value).splitlines()
        if "\u2502" in line
    )
    with pytest.raises(wgpu.GPUValidationError, match="'package::util::fill'"):
        run_test(
            wesl_device,
            compiler,
            "selected",
            source="import package::util::fill; "
            "@test fn selected() { wgsl_test::expectEq(fill(), 1u); }",
        )


@pytest.mark.gpu
def test_run_compute_file_roots_and_fill_kinds(
    wesl_device: wgpu.GPUDevice, tmp_path: Path
) -> None:
    (tmp_path / "algorithms").mkdir()
    (tmp_path / "algorithms/double.test.wesl").write_text(
        "struct Pair { count: u32, weight: f32 }"
        "@buffer var<storage, read_write> values: array<u32, 2>; "
        "@buffer var<storage, read_write> pair: Pair; "
        "@compute @workgroup_size(1) fn main() { values[0] = 2u * values[0]; }"
    )
    compiler = wesl.Compiler(root_directory=tmp_path)
    assert [
        int(
            run_compute(wesl_device, compiler, root=root, buffers={"values": [3, 4]})[
                "values"
            ][0]
        )
        for root in ("algorithms/double.test.wesl", "./algorithms/double.test.wesl")
    ] == [6, 6]
    for buffers, error, message in [
        ({"values": [1.5, 2.0]}, TypeError, "cannot fill a uint32 buffer with float64"),
        (
            {"pair": {"count": 1, "wieght": 2.0}},
            ValueError,
            r"needs the members \['count', 'weight'\], got \['count', 'wieght'\]",
        ),
    ]:
        with pytest.raises(error, match=message):
            run_compute(
                wesl_device,
                compiler,
                root="algorithms/double.test.wesl",
                buffers=buffers,
            )
    run_test_cpu(
        wesl.Compiler(
            modules={"package": "@test fn selected() { wgsl_test::expectEq(1u, 1u); }"}
        ),
        "selected",
        root="package",
    )
