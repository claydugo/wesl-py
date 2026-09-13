import package::fractal::quadratic::escape;
import package::fractal::palette::color;

override width: u32 = 640u;
override height: u32 = 480u;
@group(0) @binding(0) var<storage, read_write> pixels: array<u32>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    if (position.x >= width || position.y >= height) {
        return;
    }
    let coordinate = (vec2<f32>(position.xy) + 0.5 - vec2<f32>(f32(width), f32(height)) * 0.5)
                   * 3.0 / f32(height);
    @if(julia) let point = coordinate;
    @if(!julia) let point = coordinate - vec2<f32>(0.5, 0.0);
    pixels[position.y * width + position.x] = pack4x8unorm(vec4<f32>(color(escape(point)), 1.0));
}
