@group(0) @binding(0) var image: texture_2d<f32>;
@group(0) @binding(1) var nearest: sampler;
@group(0) @binding(2) var<uniform> multiplier: vec4f;

@fragment
fn main(@builtin(position) position: vec4f) -> @location(0) vec4f {
    let coordinate = position.xy / vec2f(textureDimensions(image));
    return textureSampleLevel(image, nearest, coordinate, 0.0) * multiplier;
}
