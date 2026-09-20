import package::levels::adjust;

@group(0) @binding(0) var output: texture_storage_2d<rgba16float, write>;

@compute @workgroup_size(4, 4)
fn main(@builtin(global_invocation_id) position: vec3u) {
    let dimensions = textureDimensions(output);
    if any(position.xy >= dimensions) {
        return;
    }
    let red = adjust(f32(position.x) / f32(dimensions.x)) * 0.5;
    let green = f32(position.y) / f32(dimensions.y);
    textureStore(output, position.xy, vec4f(red, green, 0.25, 1.0));
}
