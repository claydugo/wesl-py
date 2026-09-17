import package::levels::adjust;
import wgsl_test::expectNear;

@test
fn midpoint() {
    expectNear(adjust(0.25), 0.5);
}

@if(clamped)
@test
fn highlight() {
    expectNear(adjust(0.75), 1.0);
}

@else
@test
fn highlight() {
    expectNear(adjust(0.75), 1.5);
}

@if(clamped)
@test
fn negative_values_clamp_to_zero() {
    expectNear(adjust(-0.25), 0.0);
}
