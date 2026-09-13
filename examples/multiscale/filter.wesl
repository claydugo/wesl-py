import package::imaging::indexing::linear_index;
import package::multiscale::convolution::convolve;
import package::multiscale::tiled::convolve_tiled;

override width: u32;
override height: u32;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) invocation: vec3<u32>,
        @builtin(local_invocation_index) local_index: u32) {
    @if(horizontal) let position = vec3<u32>(invocation.xy, invocation.z + 1u);
    @if(!horizontal) let position = vec3<u32>(invocation.yx, invocation.z + 1u);
    let dimensions = vec2<u32>(width, height);
    var value = 0.0;
    @if(tiled) {
        value = convolve_tiled(position, dimensions, local_index);
    }
    if (any(position.xy >= dimensions)) {
        return;
    }
    @if(!tiled) {
        value = convolve(position, dimensions);
    }
    output[linear_index(position, dimensions)] = value;
}
