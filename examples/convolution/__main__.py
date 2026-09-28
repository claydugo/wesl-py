import argparse
from pathlib import Path

import numpy
import wesl
import wgpu


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
    random = numpy.random.default_rng(18)
    values = random.uniform(-1, 1, (3, 13, 17)).astype(numpy.float16)
    weights = random.uniform(-1, 1, (7, 3)).astype(numpy.float16)
    biases = random.uniform(-0.1, 0.1, 7).astype(numpy.float16)
    products = (weights[:, :, None, None] * values[None]).astype(numpy.float32)
    convolution = (
        products.cumsum(axis=1)[:, -1].astype(numpy.float16) + biases[:, None, None]
    )
    padded = numpy.pad(
        convolution, ((0, 0), (1, 1), (1, 1)), constant_values=-numpy.inf
    )
    pooling = numpy.lib.stride_tricks.sliding_window_view(padded, (3, 3), axis=(1, 2))[
        :, ::2, ::2
    ].max(axis=(-1, -2))
    buffers = []
    for value in [values, weights, biases]:
        payload = value.tobytes()
        buffers.append(
            device.create_buffer_with_data(
                data=payload + bytes(-len(payload) % 4), usage=wgpu.BufferUsage.STORAGE
            )
        )
    buffers.extend(
        device.create_buffer(
            size=(expected.nbytes + 3) // 4 * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        for expected in [convolution, pooling]
    )
    encoder = device.create_command_encoder()
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
        ("pooling", "main", [13, 17, 7, 3, 2, 1], [buffers[4], buffers[3]], (2, 1, 1)),
    ]:
        source = wesl.compile_file(
            Path(__file__).parent / "shaders" / f"{module}.wesl",
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
        compute = encoder.begin_compute_pass()
        compute.set_pipeline(pipeline)
        compute.set_bind_group(0, group)
        compute.dispatch_workgroups(*workgroups)
        compute.end()
    device.queue.submit([encoder.finish()])
    for buffer, expected in [(buffers[3], convolution), (buffers[4], pooling)]:
        actual = numpy.frombuffer(device.queue.read_buffer(buffer), numpy.float16)[
            : expected.size
        ].reshape(expected.shape)
        numpy.testing.assert_allclose(actual, expected, rtol=0.002, atol=0.0005)
    print(f"Convolution and pooling passed on {adapter.info['device']}")  # noqa: T201
    for buffer in buffers:
        buffer.destroy()
    device.destroy()


if __name__ == "__main__":
    main()
