from pathlib import Path
from struct import pack, unpack

import pytest
import wesl

wgpu = pytest.importorskip("wgpu")
from wesl.testing import (
    ShaderAssertionError,
    prepare_test,
    run_test,
)

pytestmark = pytest.mark.gpu


def test_shader_test_visibility(wesl_device: wgpu.GPUDevice) -> None:
    modules = {
        "package::main": (
            "import library::value; import wgsl_test::expectEq; "
            "@test @workgroup_size(2) fn selected() { expectEq(value(), 7u); }"
        ),
        "library": "fn value() -> u32 { return 7u; }",
    }
    run_test(wesl_device, modules, "selected")
    options = wesl.TestOptions(visibility=True)
    with pytest.raises(wesl.CompileError, match="visibility"):
        run_test(wesl_device, modules, "selected", options=options)
    modules["library"] = "public fn value() -> u32 { return 7u; }"
    run_test(wesl_device, modules, "selected", options=options)


@pytest.mark.parametrize(
    "override", [False, True], ids=["filesystem", "virtual-override"]
)
def test_run_test_reuses_project_dependencies(
    wesl_device: wgpu.GPUDevice, tmp_path: Path, *, override: bool
) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'alpha = { path = "common" }\nbeta = { path = "common" }\n'
    )
    common = tmp_path / "common"
    common.mkdir()
    (common / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (common / "package.wesl").write_text(
        "var<private> counter: u32 = 0u; "
        "fn next() -> u32 { counter += 1u; return counter; }"
    )
    compiler = wesl.Compiler.from_project(tmp_path)
    (tmp_path / "wesl.toml").unlink()
    (common / "wesl.toml").unlink()
    modules = {
        "package::main": "@test fn selected() { "
        "wgsl_test::expectEq(alpha::next(), 1u); "
        "wgsl_test::expectEq(beta::next(), 2u); }"
    }
    if override:
        modules["beta"] = (common / "package.wesl").read_text()
    run_test(
        wesl_device,
        modules,
        "selected",
        dependencies=compiler.dependencies,
    )
    if override:
        run_test(
            wesl_device,
            {
                "beta::tests": "@test fn selected() { "
                "wgsl_test::expectEq(package::next(), 1u); "
                "wgsl_test::expectEq(package::next(), 2u); }",
                "beta": modules["beta"],
            },
            "selected",
            root="beta::tests",
            dependencies=compiler.dependencies,
        )


def test_named_and_numeric_overrides(wesl_device: wgpu.GPUDevice) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                override offset: u32 = 0u;
                @id(3) override scale: u32 = 1u;
                @test fn overrides() {
                    wgsl_test::expectEq(offset, 7u);
                    wgsl_test::expectEq(scale, 2u);
                    wgsl_test::expectEq(library::read(), 19u);
                }
            """,
            "library": """
                override offset: u32 = 19u;
                fn read() -> u32 { return offset; }
            """,
        },
        "overrides",
        constants={"offset": 7, "3": 2},
    )


def test_repeated_runs_preserve_user_buffers_and_bindings(
    wesl_device: wgpu.GPUDevice,
) -> None:
    uniform = wesl_device.create_buffer_with_data(
        data=pack("<4I", 3, 0, 0, 0),
        usage=wgpu.BufferUsage.UNIFORM,
    )
    values = wesl_device.create_buffer_with_data(
        data=bytes(256) + pack("<I", 7),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        resources = {
            0: [{"binding": 0, "resource": {"buffer": uniform}}],
            2: [
                {"binding": 1, "resource": {"buffer": values, "offset": 256, "size": 4}}
            ],
        }
        source = """
            @group(0) @binding(0) var<uniform> increment: vec4u;
            @group(2) @binding(1) var<storage, read_write> value: u32;
            override expected: u32 = 0u;
            @test fn mutate() {
                value += increment.x;
                wgsl_test::expectEq(value, expected);
            }
        """
        for expected in (10, 13):
            run_test(
                wesl_device,
                {"package::main": source},
                "mutate",
                resources=resources,
                constants={"expected": expected},
            )
        assert len(resources[0]) == 1
        assert unpack(
            "<I", wesl_device.queue.read_buffer(values, buffer_offset=256, size=4)
        ) == (13,)
    finally:
        values.destroy()
        uniform.destroy()


def test_prepared_test_resets_results_and_preserves_default_resources(
    wesl_device: wgpu.GPUDevice,
) -> None:
    uniform = wesl_device.create_buffer_with_data(
        data=pack("<4I", 3, 0, 0, 0),
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    try:
        shader_test = prepare_test(
            wesl_device,
            {
                "package::main": "@group(0) @binding(0) var<uniform> value: vec4u; "
                "@test fn selected() { wgsl_test::expectEq(value.x, 7u); }"
            },
            "selected",
            resources={0: [{"binding": 0, "resource": {"buffer": uniform}}]},
        )
        with pytest.raises(ShaderAssertionError) as failure:
            shader_test()
        assert failure.value.checks == 1
        assert failure.value.failures == 1
        replacement = wesl_device.create_buffer_with_data(
            data=pack("<4I", 7, 0, 0, 0),
            usage=wgpu.BufferUsage.UNIFORM,
        )
        try:
            shader_test(
                resources={0: [{"binding": 0, "resource": {"buffer": replacement}}]}
            )
        finally:
            replacement.destroy()
        with pytest.raises(ShaderAssertionError) as failure:
            shader_test()
        assert failure.value.checks == 1
        assert failure.value.failures == 1
        wesl_device.queue.write_buffer(uniform, 0, pack("<4I", 7, 0, 0, 0))
        shader_test()
        shader_test()
    finally:
        uniform.destroy()


def test_texture_bindings(wesl_device: wgpu.GPUDevice) -> None:
    texture = wesl_device.create_texture(
        size=(1, 1, 1),
        format="rgba8unorm",
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    try:
        wesl_device.queue.write_texture(
            {"texture": texture},
            bytes((255, 0, 0, 255)),
            {"bytes_per_row": 4},
            (1, 1, 1),
        )
        run_test(
            wesl_device,
            {
                "package::main": """
                @group(2) @binding(0) var image: texture_2d<f32>;
                @group(2) @binding(1) var nearest: sampler;
                @test fn sample() {
                    wgsl_test::expectNearVec4(
                        textureSampleLevel(image, nearest, vec2f(0.5), 0.0),
                        vec4f(1.0, 0.0, 0.0, 1.0),
                    );
                }
            """
            },
            "sample",
            resources={
                2: [
                    {"binding": 0, "resource": texture.create_view()},
                    {"binding": 1, "resource": wesl_device.create_sampler()},
                ]
            },
        )
    finally:
        texture.destroy()


@pytest.mark.parametrize(
    ("group", "texture_format", "channel_count"),
    [(0, "r32float", 1), (2, "rgba32float", 4)],
)
def test_float32_texture_bindings(
    wesl_device: wgpu.GPUDevice, group: int, texture_format: str, channel_count: int
) -> None:
    assert "float32-filterable" not in wesl_device.features
    texture = wesl_device.create_texture(
        size=(1, 1, 1),
        format=texture_format,
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    try:
        wesl_device.queue.write_texture(
            {"texture": texture},
            pack("<f", 1.0000009536743164) * channel_count,
            {"bytes_per_row": 4 * channel_count},
            (1, 1, 1),
        )
        resources = {
            group: [
                {"binding": 0, "resource": texture.create_view()},
                {
                    "binding": 1,
                    "resource": wesl_device.create_sampler(
                        mag_filter="nearest",
                        min_filter="nearest",
                        mipmap_filter="nearest",
                    ),
                },
            ]
        }
        layouts = {
            group: [
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
                "package::main": f"""
                    @group({group}) @binding(0) var image: texture_2d<f32>;
                    @group({group}) @binding(1) var nearest: sampler;
                    @test fn sample() {{
                        wgsl_test::expectUlp(
                            textureSampleLevel(image, nearest, vec2f(0.5), 0.0).x,
                            1.0000009536743164,
                            0u,
                        );
                    }}
                """
            },
            "sample",
            resources=resources,
            layouts=layouts,
        )
        assert len(resources[group]) == 2
        assert len(layouts[group]) == 2
        assert set(layouts) == {group}
    finally:
        texture.destroy()
