from collections.abc import Callable

import pytest

np = pytest.importorskip("numpy")

pytestmark = pytest.mark.gpu


@pytest.mark.parametrize(
    (
        "entry_point",
        "height",
        "width",
        "channels",
        "output_channels",
        "kernel",
        "stride",
        "padding",
        "activation",
        "precision",
    ),
    [
        pytest.param(
            "tiled", 5, 7, [3], 19, 1, 1, 0, 0, "reference", id="pointwise-tail"
        ),
        pytest.param(
            "direct", 7, 9, [3], 7, 3, 2, 1, 1, "wide_products", id="rgb-stride-padding"
        ),
        pytest.param(
            "pointwise", 5, 7, [3, 2], 19, 1, 1, 0, 1, "wide", id="pointwise-wide"
        ),
        pytest.param(
            "tiled",
            4,
            11,
            [3, 2, 4, 1],
            18,
            1,
            1,
            0,
            2,
            "wide",
            id="sigmoid-four-inputs",
        ),
        pytest.param(
            "direct", 5, 7, [3], 6, 3, 1, 1, 2, "reference", id="spatial-sigmoid"
        ),
    ],
)
def test_convolution_matches_numpy(
    assert_operator: Callable[..., None],
    *,
    entry_point: str,
    height: int,
    width: int,
    channels: list[int],
    output_channels: int,
    kernel: int,
    stride: int,
    padding: int,
    activation: int,
    precision: str,
) -> None:
    random = np.random.default_rng(51)
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
    expected = (total if precision == "wide" else total.astype(np.float16)) + biases[
        :, None, None
    ]
    if activation == 1:
        expected = np.where(
            expected < 0,
            expected * (np.float32(0.1) if precision == "wide" else np.float16(0.1)),
            expected,
        )
    if activation == 2 and precision == "wide":
        expected = 1 / (1 + np.exp(-expected))
        expected = expected.reshape(-1, 6, output_height, output_width).transpose(
            0, 2, 3, 1
        )
    elif activation == 2:
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

    assert_operator(
        operation="convolution",
        entry_point=entry_point,
        payloads=payloads,
        expected=expected,
        constants=constants,
        workgroups=workgroups,
        tolerance=(0.002, 0.0005),
    )


@pytest.mark.parametrize(
    ("height", "width", "channels", "kernel", "stride", "padding"),
    [
        pytest.param(5, 7, 3, 2, 2, 0, id="pool-stride-tail"),
        pytest.param(5, 7, 3, 13, 1, 6, id="pool-thirteen"),
    ],
)
def test_pooling_matches_numpy(
    assert_operator: Callable[..., None],
    *,
    height: int,
    width: int,
    channels: int,
    kernel: int,
    stride: int,
    padding: int,
) -> None:
    random = np.random.default_rng(51)
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

    assert_operator(
        operation="pooling",
        entry_point="main",
        payloads=payloads,
        expected=expected,
        constants=constants,
        workgroups=workgroups,
        tolerance=(0.0, 0.0),
    )


def test_resize_matches_numpy(
    assert_operator: Callable[..., None],
) -> None:
    random = np.random.default_rng(51)
    height, width, channels, scale = 3, 5, 2, 2
    values = random.normal(size=(channels, height, width)).astype(np.float16)
    expected = values.repeat(scale, axis=1).repeat(scale, axis=2)
    payloads = [values]
    constants = dict(enumerate([height, width, channels, scale]))
    workgroups = ((expected.size + 255) // 256, 1, 1)

    assert_operator(
        operation="resize",
        entry_point="main",
        payloads=payloads,
        expected=expected,
        constants=constants,
        workgroups=workgroups,
        tolerance=(0.0, 0.0),
    )
