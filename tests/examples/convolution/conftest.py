from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import wesl

if TYPE_CHECKING:
    import wgpu


@pytest.fixture
def wesl_dependencies() -> dict[str, Path]:
    return {"operators": Path(__file__).parents[3] / "examples/convolution/shaders"}


@pytest.fixture(
    params=[
        pytest.param(
            ("convolution", "tiled", 5, 7, [3], 19, 1, 1, 0, 0), id="pointwise-tail"
        ),
        pytest.param(
            ("convolution", "tiled", 7, 9, [3], 7, 3, 2, 1, 1), id="tiled-spatial"
        ),
        pytest.param(
            ("convolution", "tiled", 4, 11, [3, 2, 4, 1], 17, 1, 1, 0, 1),
            id="four-inputs",
        ),
        pytest.param(
            ("convolution", "tiled", 3, 13, [5], 18, 1, 1, 0, 2), id="sigmoid-layout"
        ),
        pytest.param(
            ("convolution", "direct", 7, 9, [3], 7, 3, 2, 1, 1), id="rgb-stride-padding"
        ),
        pytest.param(
            ("convolution", "direct", 5, 9, [2, 3], 6, 3, 1, 1, 1),
            id="two-inputs-spatial",
        ),
        pytest.param(
            ("convolution", "direct", 7, 11, [5], 19, 3, 1, 1, 0), id="spatial-tail"
        ),
        pytest.param(
            ("convolution", "direct", 5, 7, [3], 6, 3, 1, 1, 2), id="spatial-sigmoid"
        ),
        pytest.param(
            ("convolution", "pointwise", 5, 7, [3, 2], 19, 1, 1, 0, 1),
            id="pointwise-direct-tail",
        ),
        pytest.param(("pooling", 5, 7, 3, 2, 2, 0), id="pool-stride-tail"),
        pytest.param(("pooling", 5, 7, 3, 5, 1, 2), id="pool-five"),
        pytest.param(("pooling", 5, 7, 3, 9, 1, 4), id="pool-nine"),
        pytest.param(("pooling", 5, 7, 3, 13, 1, 6), id="pool-thirteen"),
        pytest.param(("resize", 3, 5, 2, 2), id="nearest-two"),
    ]
)
def wesl_resources(  # noqa: C901, PLR0915
    request: pytest.FixtureRequest,
    wesl_device: "wgpu.GPUDevice",
    precision: str,
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    np = pytest.importorskip("numpy")
    wgpu = pytest.importorskip("wgpu")
    operation, *parameters = request.param
    entry_point = "main"
    random = np.random.default_rng(51)
    if operation == "convolution":
        (
            entry_point,
            height,
            width,
            channels,
            output_channels,
            kernel,
            stride,
            padding,
            activation,
        ) = parameters
        inputs = [
            random.uniform(-1, 1, (count, height, width)).astype(np.float16)
            for count in channels
        ]
        weights = random.uniform(
            -0.25, 0.25, (output_channels, sum(channels), kernel, kernel)
        ).astype(np.float16)
        biases = random.uniform(-0.1, 0.1, output_channels).astype(np.float16)
        padded = np.pad(
            np.concatenate(inputs), ((0, 0), (padding, padding), (padding, padding))
        )
        windows = np.lib.stride_tricks.sliding_window_view(
            padded, (kernel, kernel), axis=(1, 2)
        )
        windows = windows[:, ::stride, ::stride].transpose(0, 3, 4, 1, 2)
        output_height, output_width = windows.shape[-2:]
        if precision != "reference":
            weights = weights.astype(np.float32)
            windows = windows.astype(np.float32)
        products = (
            weights.reshape(output_channels, -1, 1, 1)
            * windows.reshape(1, -1, output_height, output_width)
        ).astype(np.float32)
        total = products.cumsum(axis=1)[:, -1]
        expected = (
            total if precision == "wide" else total.astype(np.float16)
        ) + biases[:, None, None]
        if activation == 1:
            expected = np.where(
                expected < 0,
                expected
                * (np.float32(0.1) if precision == "wide" else np.float16(0.1)),
                expected,
            )
        if activation == 2 and precision == "wide":  # noqa: PLR2004
            expected = 1 / (1 + np.exp(-expected))
            expected = expected.reshape(-1, 6, output_height, output_width).transpose(
                0, 2, 3, 1
            )
        elif activation == 2:  # noqa: PLR2004
            expected = np.float16(1) / (
                np.float16(1) + np.exp2(expected * np.float16(-1.4423828125))
            )
            expected = expected.reshape(-1, 6, output_height, output_width).transpose(
                0, 2, 3, 1
            )
        payloads = [
            *inputs,
            *([inputs[0]] * (4 - len(inputs))),
            weights.astype(np.float16),
            biases,
        ]
        constants = dict(
            enumerate(
                [
                    height,
                    width,
                    sum(channels),
                    output_channels,
                    kernel,
                    stride,
                    padding,
                    activation,
                    *[*channels, 0, 0, 0][:3],
                ]
            )
        )
        constants[11] = precision != "reference"
        constants[12] = precision == "wide"
        expected = expected.astype(np.float16)
        workgroups = (
            (output_height * output_width + 31) // 32,
            (output_channels + 15) // 16,
            1,
        )
        if entry_point == "pointwise":
            workgroups = (
                (output_height * output_width + 511) // 512,
                (output_channels + 3) // 4,
                1,
            )
        if entry_point == "direct":
            workgroups = (
                (((output_width + 2) // 3) * output_height + 127) // 128,
                (output_channels + 3) // 4,
                1,
            )
    elif operation == "pooling":
        height, width, channels, kernel, stride, padding = parameters
        values = random.uniform(-4, -1, (channels, height, width)).astype(np.float16)
        padded = np.pad(
            values,
            ((0, 0), (padding, padding), (padding, padding)),
            constant_values=-np.inf,
        )
        expected = np.lib.stride_tricks.sliding_window_view(
            padded,
            (kernel, kernel),
            axis=(1, 2),
        )[:, ::stride, ::stride].max(axis=(-1, -2))
        payloads = [values]
        constants = dict(enumerate([height, width, channels, kernel, stride, padding]))
        workgroups = ((expected.size + 255) // 256, 1, 1)
    elif operation == "resize":
        height, width, channels, scale = parameters
        values = random.normal(size=(channels, height, width)).astype(np.float16)
        expected = values.repeat(scale, axis=1).repeat(scale, axis=2)
        payloads = [values]
        constants = dict(enumerate([height, width, channels, scale]))
        workgroups = ((expected.size + 255) // 256, 1, 1)
    expected = np.concatenate(
        [
            expected.ravel(),
            np.full(16 + expected.size % 2, 123, dtype=np.float16),
        ]
    )
    buffers = [
        wesl_device.create_buffer_with_data(
            data=np.full(expected.size, 123, dtype=np.float16),
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
    ]
    for payload in payloads:
        data = payload.tobytes()
        buffers.append(
            wesl_device.create_buffer_with_data(
                data=data + bytes(-len(data) % 4),
                usage=wgpu.BufferUsage.STORAGE,
            )
        )
    source = wesl.compile_file(
        Path(__file__).parents[3]
        / "examples/convolution/shaders"
        / f"{operation}.wesl",
        options=wesl.CompileOptions(visibility=True),
    ).wgsl
    pipeline = wesl_device.create_compute_pipeline(
        layout="auto",
        compute={
            "module": wesl_device.create_shader_module(code=source),
            "entry_point": entry_point,
            "constants": {str(key): value for key, value in constants.items()},
        },
    )
    group = wesl_device.create_bind_group(
        layout=pipeline.get_bind_group_layout(0),
        entries=[
            {"binding": index, "resource": {"buffer": buffer}}
            for index, buffer in enumerate(buffers)
        ],
    )
    encoder = wesl_device.create_command_encoder()
    compute = encoder.begin_compute_pass()
    compute.set_pipeline(pipeline)
    compute.set_bind_group(0, group)
    compute.dispatch_workgroups(*workgroups)
    compute.end()
    wesl_device.queue.submit([encoder.finish()])
    reference = wesl_device.create_buffer_with_data(
        data=expected, usage=wgpu.BufferUsage.STORAGE
    )
    tolerance = wesl_device.create_buffer_with_data(
        data=np.array(
            [0.002, 0.0005] if operation == "convolution" else [0, 0], dtype=np.float32
        ),
        usage=wgpu.BufferUsage.UNIFORM,
    )
    yield {
        0: [
            {"binding": 0, "resource": {"buffer": buffers[0]}},
            {"binding": 1, "resource": {"buffer": reference}},
            {"binding": 2, "resource": {"buffer": tolerance}},
        ]
    }
    for buffer in [*buffers, reference, tolerance]:
        buffer.destroy()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--convolution-adapter", default=None)


@pytest.fixture(scope="session")
def wesl_device(request: pytest.FixtureRequest) -> Iterator["wgpu.GPUDevice"]:
    wgpu = pytest.importorskip("wgpu")
    name = request.config.getoption("--convolution-adapter")
    if name is None:
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    else:
        adapter = next(
            adapter
            for adapter in wgpu.gpu.enumerate_adapters_sync()
            if name.lower() in adapter.info["device"].lower()
            and adapter.info["backend_type"] == "Vulkan"
        )
    if "shader-f16" not in adapter.features:
        pytest.skip("The adapter does not support shader-f16.")
    device = adapter.request_device_sync(required_features=["shader-f16"])
    yield device
    device.destroy()


@pytest.fixture(params=["reference", "wide_products", "wide"])
def precision(request: pytest.FixtureRequest) -> str:
    return request.param
