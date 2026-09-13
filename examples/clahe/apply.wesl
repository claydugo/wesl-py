import package::imaging::indexing::linear_index;
import package::clahe::interpolation::interpolate;

override width: u32;
override height: u32;
override tile_size: u32 = 64u;
@group(0) @binding(0) var<storage, read> source: array<f32>;
@group(0) @binding(2) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    let dimensions = vec2<u32>(width, height);
    if (any(position.xy >= dimensions)) {
        return;
    }
    let index = linear_index(position, dimensions);
    let value = u32(round(clamp(source[index], 0.0, 1.0) * 255.0));
    let tile_count = (dimensions + tile_size - 1u) / tile_size;
    output[index] = interpolate(position, value, tile_size, tile_count);
}
