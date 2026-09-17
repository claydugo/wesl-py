@if(clamped)
fn adjust(value: f32) -> f32 {
    return clamp(value * 2.0, 0.0, 1.0);
}

@else
fn adjust(value: f32) -> f32 {
    return value * 2.0;
}
