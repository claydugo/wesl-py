@group(0) @binding(1) var<storage, read> colors: array<vec4<f32>>;

fn channel_color(value: f32, channel: u32) -> vec3<f32> {
    let position = clamp(value, 0.0, 1.0) * 255.0;
    let lower = u32(position);
    let upper = min(lower + 1u, 255u);
    return mix(colors[channel * 256u + lower].rgb,
               colors[channel * 256u + upper].rgb, fract(position));
}
