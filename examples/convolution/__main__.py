import argparse
from contextlib import ExitStack
from pathlib import Path

import numpy as np
import wesl
import wgpu
from wesl.testing import prepare_test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=None)
    arguments = parser.parse_args()
    if arguments.adapter is None:
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    else:
        adapter = next(
            adapter
            for adapter in wgpu.gpu.enumerate_adapters_sync()
            if arguments.adapter.lower() in adapter.info["device"].lower()
            and adapter.info["backend_type"] == "Vulkan"
        )
    device = adapter.request_device_sync(required_features=["shader-f16"])
    random = np.random.default_rng(18)
    weights = random.uniform(-1, 1, (7, 3)).astype(np.float16)
    biases = random.uniform(-0.1, 0.1, 7).astype(np.float16)
    with ExitStack() as stack:
        stack.callback(device.destroy)
        buffers = []
        for value in [np.zeros((3, 13, 17), dtype=np.float16), weights, biases]:
            payload = value.tobytes()
            buffer = device.create_buffer_with_data(
                data=payload + bytes(-len(payload) % 4),
                usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
            )
            stack.callback(buffer.destroy)
            buffers.append(buffer)
        for shape in [(7, 13, 17), (7, 7, 9)]:
            buffer = device.create_buffer(
                size=(np.prod(shape).item() * 2 + 3) // 4 * 4,
                usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
            )
            stack.callback(buffer.destroy)
            buffers.append(buffer)
        references = []
        for buffer in [buffers[3], buffers[4]]:
            reference = device.create_buffer(
                size=buffer.size,
                usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
            )
            stack.callback(reference.destroy)
            references.append(reference)
        passes = []
        for module, entry, constants, bindings, workgroups in [
            (
                "convolution",
                "tiled",
                [13, 17, 3, 7, 1, 1, 0, 0, 3, 0, 0],
                [
                    buffers[3],
                    buffers[0],
                    buffers[0],
                    buffers[0],
                    buffers[0],
                    buffers[1],
                    buffers[2],
                ],
                (7, 1, 1),
            ),
            (
                "pooling",
                "main",
                [13, 17, 7, 3, 2, 1],
                [buffers[4], buffers[3]],
                (2, 1, 1),
            ),
        ]:
            source = wesl.compile_file(
                Path(__file__).parent / "shaders" / f"{module}.wesl",
                root_directory=Path(__file__).parents[2],
                options=wesl.CompileOptions(visibility=True),
            ).wgsl
            pipeline = device.create_compute_pipeline(
                layout="auto",
                compute={
                    "module": device.create_shader_module(code=source),
                    "entry_point": entry,
                    "constants": {
                        str(index): value for index, value in enumerate(constants)
                    },
                },
            )
            group = device.create_bind_group(
                layout=pipeline.get_bind_group_layout(0),
                entries=[
                    {"binding": index, "resource": {"buffer": buffer}}
                    for index, buffer in enumerate(bindings)
                ],
            )
            passes.append((pipeline, group, workgroups))
        verify = prepare_test(
            device,
            {
                "package::main": (
                    Path(__file__).parent / "shaders/verify.wesl"
                ).read_text()
            },
            "matches_reference",
            filenames={"package::main": Path(__file__).parent / "shaders/verify.wesl"},
            resources={
                0: [
                    {"binding": 0, "resource": {"buffer": buffers[3]}},
                    {"binding": 1, "resource": {"buffer": references[0]}},
                ]
            },
        )
        for _ in range(3):
            values = random.uniform(-1, 1, (3, 13, 17)).astype(np.float16)
            products = (weights[:, :, None, None] * values[None]).astype(np.float32)
            convolution = (
                products.cumsum(axis=1)[:, -1].astype(np.float16)
                + biases[:, None, None]
            )
            padded = np.pad(
                convolution, ((0, 0), (1, 1), (1, 1)), constant_values=-np.inf
            )
            pooling = np.lib.stride_tricks.sliding_window_view(
                padded, (3, 3), axis=(1, 2)
            )[:, ::2, ::2].max(axis=(-1, -2))
            payload = values.tobytes()
            device.queue.write_buffer(buffers[0], 0, payload + bytes(-len(payload) % 4))
            encoder = device.create_command_encoder()
            for pipeline, group, workgroups in passes:
                compute = encoder.begin_compute_pass()
                compute.set_pipeline(pipeline)
                compute.set_bind_group(0, group)
                compute.dispatch_workgroups(*workgroups)
                compute.end()
            device.queue.submit([encoder.finish()])
            for reference, expected in zip(
                references, [convolution, pooling], strict=True
            ):
                payload = expected.tobytes()
                device.queue.write_buffer(
                    reference, 0, payload + bytes(-len(payload) % 4)
                )
            verify()
            verify(
                resources={
                    0: [
                        {"binding": 0, "resource": {"buffer": buffers[4]}},
                        {"binding": 1, "resource": {"buffer": references[1]}},
                    ]
                }
            )
        print(f"Convolution and pooling passed on {adapter.info['device']}")


if __name__ == "__main__":
    main()
