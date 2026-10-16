from __future__ import annotations

from contextlib import ExitStack
from struct import pack
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    import wgpu


@pytest.fixture
def wesl_layouts(wesl_device: wgpu.GPUDevice) -> dict[int, list[dict[str, Any]]]:
    wgpu = pytest.importorskip("wgpu")
    assert "float32-filterable" not in wesl_device.features
    return {
        0: [
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": "uniform"},
            }
        ],
        2: [
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "texture": {"sample_type": "float"},
            },
            {
                "binding": 1,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "texture": {"sample_type": "unfilterable-float"},
            },
            {
                "binding": 2,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "sampler": {"type": "non-filtering"},
            },
            {
                "binding": 3,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": "read-only-storage"},
            },
        ],
    }


@pytest.fixture
def wesl_resources(
    wesl_device: wgpu.GPUDevice,
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    wgpu = pytest.importorskip("wgpu")
    with ExitStack() as stack:
        textures = []
        for texture_format, data in (
            ("rgba8unorm", bytes((255, 0, 0, 255))),
            ("rgba32float", pack("<f", 1.0000009536743164) * 4),
        ):
            texture = wesl_device.create_texture(
                size=(1, 1, 1),
                format=texture_format,
                usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
            )
            stack.callback(texture.destroy)
            wesl_device.queue.write_texture(
                {"texture": texture}, data, {"bytes_per_row": len(data)}, (1, 1, 1)
            )
            textures.append(texture)
        increment = wesl_device.create_buffer_with_data(
            data=pack("<4I", 3, 0, 0, 0), usage=wgpu.BufferUsage.UNIFORM
        )
        stack.callback(increment.destroy)
        stored = wesl_device.create_buffer_with_data(
            data=bytes(256) + pack("<I", 7), usage=wgpu.BufferUsage.STORAGE
        )
        stack.callback(stored.destroy)
        yield {
            0: [{"binding": 0, "resource": {"buffer": increment}}],
            2: [
                {"binding": 0, "resource": textures[0].create_view()},
                {"binding": 1, "resource": textures[1].create_view()},
                {
                    "binding": 2,
                    "resource": wesl_device.create_sampler(
                        mag_filter="nearest", min_filter="nearest"
                    ),
                },
                {
                    "binding": 3,
                    "resource": {"buffer": stored, "offset": 256, "size": 4},
                },
            ],
        }
