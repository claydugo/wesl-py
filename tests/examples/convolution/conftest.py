from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    import numpy as np
    import wgpu


@pytest.fixture
def assert_operator(
    wesl_device: "wgpu.GPUDevice",
    wesl_test_options: wesl.TestOptions,
) -> Callable[..., None]:
    np = pytest.importorskip("numpy")
    wgpu = pytest.importorskip("wgpu")
    from wesl.testing import run_test

    def check(
        *,
        operation: str,
        entry_point: str,
        payloads: list["np.ndarray"],
        expected: "np.ndarray",
        constants: dict[int, int | bool],
        workgroups: tuple[int, int, int],
        tolerance: tuple[float, float],
    ) -> None:
        expected_count = expected.size
        expected = np.concatenate(
            [
                expected.ravel(),
                np.full(16 + expected.size % 2, 123, dtype=np.float16),
            ]
        )
        with ExitStack() as stack:
            buffers = [
                wesl_device.create_buffer_with_data(
                    data=np.full(expected.size, 123, dtype=np.float16),
                    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
                )
            ]
            stack.callback(buffers[0].destroy)
            for payload in payloads:
                data = payload.tobytes()
                buffers.append(
                    wesl_device.create_buffer_with_data(
                        data=data + bytes(-len(data) % 4),
                        usage=wgpu.BufferUsage.STORAGE,
                    )
                )
                stack.callback(buffers[-1].destroy)
            source = wesl.compile_file(
                Path(__file__).parents[3]
                / "examples/convolution/shaders"
                / f"{operation}.wesl",
                root_directory=Path(__file__).parents[3],
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
            stack.callback(reference.destroy)
            tolerance_buffer = wesl_device.create_buffer_with_data(
                data=np.array(tolerance, dtype=np.float32),
                usage=wgpu.BufferUsage.UNIFORM,
            )
            stack.callback(tolerance_buffer.destroy)
            filename = Path(__file__).with_name("operators.wesl")
            run_test(
                wesl_device,
                wesl.Compiler(
                    modules={"package::main": filename.read_text()},
                    filenames={"package::main": filename},
                ),
                "operator_matches_reference",
                options=wesl_test_options,
                constants={"expected_count": expected_count},
                resources={
                    0: [
                        {"binding": 0, "resource": {"buffer": buffers[0]}},
                        {"binding": 1, "resource": {"buffer": reference}},
                        {"binding": 2, "resource": {"buffer": tolerance_buffer}},
                    ]
                },
            )

    return check


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
            (
                adapter
                for adapter in wgpu.gpu.enumerate_adapters_sync()
                if name.lower() in adapter.info["device"].lower()
                and adapter.info["backend_type"] == "Vulkan"
            ),
            None,
        )
        if adapter is None:
            message = "No Vulkan adapter matches --convolution-adapter."
            raise pytest.UsageError(message)
    if "shader-f16" not in adapter.features:
        pytest.skip("The adapter does not support shader-f16.")
    device = adapter.request_device_sync(required_features=["shader-f16"])
    yield device
    device.destroy()
