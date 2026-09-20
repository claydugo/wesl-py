import pytest
import wesl
from pytest_regressions.ndarrays_regression import NDArraysRegressionFixture
from wesl.testing import ShaderRunner


@pytest.mark.gpu
def test_gradient(
    wesl_compiler: wesl.Compiler,
    wesl_runner: ShaderRunner,
    ndarrays_regression: NDArraysRegressionFixture,
) -> None:
    shader = wesl_compiler.compile_file("gradient.wesl")
    pixels = wesl_runner.fragment(shader, size=(8, 4))
    ndarrays_regression.check(
        {"pixels": pixels},
        default_tolerance={"rtol": 1e-6, "atol": 1e-7},
    )
