from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from struct import pack, unpack
from typing import TYPE_CHECKING

import pytest
import wesl
from wesl.testing import (
    ShaderAssertionError,
    prepare_test,
    run_test,
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
    shader_runner(modules, "selected")
    options = wesl.TestOptions(visibility=True)
    with pytest.raises(wesl.CompileError, match="visibility"):
        shader_runner(modules, "selected", options=options)
    modules["library"] = "public fn value() -> u32 { return 7u; }"
    shader_runner(modules, "selected", options=options)


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
        modules,
        "selected",
        dependencies={"common": common},
    )


@pytest.mark.gpu
def test_prepared_test_lifecycle(wesl_device: wgpu.GPUDevice) -> None:
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
                override expected: u32 = 0u;
                @test fn accumulate() {
                    value += increment.x;
                    wgsl_test::expectEq(value, expected);
                    wgsl_test::expectNearVec4(
                        textureSampleLevel(image, linear, vec2f(0.5), 0.0),
                        vec4f(1.0, 0.0, 0.0, 1.0),
                    );
                }
            """
        }
        run_test(
            wesl_device,
            modules,
            "accumulate",
            resources=resources,
            constants={"expected": 7},
        )
        shader_test = prepare_test(
            wesl_device,
            modules,
            "accumulate",
            resources=resources,
            constants={"expected": 10},
        )
        shader_test()
        for replacement in (None, bindings(buffers[1], buffers[3]), None):
            if replacement is None:
                with pytest.raises(ShaderAssertionError) as failure:
                    shader_test()
                assert (failure.value.checks, failure.value.failures) == (2, 1)
            else:
                shader_test(resources=replacement)
        wesl_device.queue.write_buffer(buffers[2], 256, pack("<I", 7))
        shader_test()
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
            {
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
            },
            "sample",
            resources=resources,
            layouts=layouts,
        )
        assert [len(entries) for entries in resources.values()] == [2]
        assert [len(entries) for entries in layouts.values()] == [2]
    finally:
        texture.destroy()


def test_constants_for_stripped_overrides(shader_runner: partial) -> None:
    modules = {
        "package::main": """
            import package::library::helper;
            const base = 8u;
            override used: u32;
            override unused: u32;
            @id(9) override numbered: u32;
            @id(base + 2u) override derived: u32;
            @test fn selected() { wgsl_test::expectEq(used + helper(), 7u); }
        """,
        "package::library": """
            @id(11) override imported: u32;
            override hidden: u32 = 0u;
            fn helper() -> u32 { return 0u; }
        """,
    }
    shader_runner(
        modules,
        "selected",
        constants={"used": 7, "unused": 1, "9": 2, "10": 3, "11": 4},
    )
    error_types: tuple[type[Exception], ...] = (ValueError,)
    if find_spec("wgpu") is not None:
        error_types = (ValueError, import_module("wgpu").GPUValidationError)
    for name in ["misspelled", "numbered", "hidden"]:
        with pytest.raises(
            error_types,
            match=r"pipeline constant does not name an override"
            r"|pipeline-overridable constant '[a-z_]+' not found",
        ):
            shader_runner(modules, "selected", constants={"used": 7, name: 1})
