import package::levels::adjust;

@fragment
fn main(@builtin(position) position: vec4f) -> @location(0) vec4f {
    return vec4f(adjust(position.x / 8.0 - 0.25), position.y / 4.0, 0.25, 1.0);
}
