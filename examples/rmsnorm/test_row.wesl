import package::rmsnorm::input::load;
import package::rmsnorm::normalization::scale;
import wgsl_test::expectNear;

@test
fn row_contract() {
    @if(residual) {
        expectNear(load(0u), 3.0);
        expectNear(load(1u), -3.0);
    }
    @else {
        expectNear(load(0u), 2.0);
        expectNear(load(1u), -2.0);
    }
    expectNear(scale(1.5), 1.0);
    expectNear(scale(7.5), 0.5);
}
