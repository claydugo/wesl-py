import super::levels::adjust;
import wgsl_test::{expect, expectNear};

@test @workgroup_size(64)
fn transfer_curve(@builtin(local_invocation_index) lane: u32) {
    let value = f32(lane) / 32.0 - 0.5;
    expect(adjust(value) <= adjust(value + 0.03125));
    @if(clamped) {
        expectNear(adjust(value), clamp(2.0 * value, 0.0, 1.0));
    }
    @else {
        expectNear(adjust(value), 2.0 * value);
    }
}

@if(clamped)
@test
fn negative_values_clamp_to_zero() {
    expectNear(adjust(-0.25), 0.0);
}
