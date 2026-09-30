from pathlib import Path

import pytest

wgpu = pytest.importorskip("wgpu")
from wesl.testing import run_test


@pytest.mark.gpu
def test_activation(
    wesl_device: wgpu.GPUDevice,
    wesl_root_directory: Path,
) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                import package::examples::convolution::shaders::activation::activate;
                enable f16;
                @test fn selected() {
                    wgsl_test::expectWithin(
                        f32(activate(-2.0, 0.0h, 0u)), -2.0, 0.0, 0.0,
                    );
                    wgsl_test::expectWithin(
                        f32(activate(-10.0, 0.0h, 1u)), -1.0, 0.0, 0.0,
                    );
                    wgsl_test::expectWithin(
                        f32(activate(0.0, 0.0h, 2u)), 0.5, 0.0, 0.0,
                    );
                }
            """,
        },
        "selected",
        root_directory=wesl_root_directory,
    )
