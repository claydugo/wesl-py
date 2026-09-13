import package::imaging::indexing::linear_index;
import package::imaging::color::channel_color;

@group(0) @binding(0) var<storage, read> channels: array<f32>;
@group(0) @binding(2) var output: texture_storage_2d<rgba8unorm, write>;
@group(0) @binding(3) var<uniform> weights: vec4<f32>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    let dimensions = textureDimensions(output);
    if (any(position.xy >= dimensions)) {
        return;
    }
    let brightfield = channels[linear_index(vec3<u32>(position.xy, 0u), dimensions)];
    let gfp = channels[linear_index(vec3<u32>(position.xy, 1u), dimensions)];
    let rfp = channels[linear_index(vec3<u32>(position.xy, 2u), dimensions)];
    let color = weights.x * channel_color(brightfield, 0u)
              + weights.y * channel_color(gfp, 1u)
              + weights.z * channel_color(rfp, 2u);
    textureStore(output, position.xy,
                 vec4<f32>(clamp(color, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0));
}
