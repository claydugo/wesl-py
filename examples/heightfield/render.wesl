import package::heightfield::surface::{gradient, normal};
import package::heightfield::lighting::illuminate;

override width: u32;
override height: u32;
override light_x: f32;
override light_y: f32;
override light_z: f32;
@group(0) @binding(1) var<storage, read_write> pixels: array<u32>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) invocation: vec3<u32>) {
    if (invocation.x >= width || invocation.y >= height) {
        return;
    }
    let position = vec2<i32>(invocation.xy);
    let dimensions = vec2<u32>(width, height);
    @if(edges) let color = vec3<f32>(1.0 - exp(-length(gradient(position, dimensions))));
    @if(normals) let color = 0.5 + 0.5 * normal(position, dimensions);
    @if(shaded) let color = illuminate(normal(position, dimensions), vec3<f32>(light_x, light_y, light_z));
    pixels[invocation.y * width + invocation.x] = pack4x8unorm(vec4<f32>(color, 1.0));
}
