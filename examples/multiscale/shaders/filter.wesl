import package::imaging::indexing::linear_index;
import package::imaging::gaussian::convolve;

override width: u32;
override height: u32;
override first_field: u32 = 0u;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) invocation: vec3<u32>) {
    @if(horizontal) let position = vec3<u32>(invocation.xy, invocation.z + first_field);
    @if(!horizontal) let position = vec3<u32>(invocation.yx, invocation.z + first_field);
    let dimensions = vec2<u32>(width, height);
    if (any(position.xy >= dimensions)) {
        return;
    }
    output[linear_index(position, dimensions)] = convolve(position, dimensions);
}
