import package::imaging::statistics::{Moments, correlation};
import package::imaging::sampling::clamp_position;
import package::imaging::gaussian::{radius, weights};

override width: u32;
override height: u32;
override maximum_brightfield: f32 = 0.9;
@group(0) @binding(0) var<storage, read> channels: array<f32>;
@if(horizontal) @group(0) @binding(1) var<storage, read_write> output: array<Moments>;
@if(!horizontal) @group(0) @binding(1) var<storage, read_write> output: array<vec2<f32>>;
@if(!horizontal) @group(0) @binding(3) var<storage, read> partials: array<Moments>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) invocation: vec3<u32>) {
    @if(horizontal) let position = invocation.xy;
    @if(!horizontal) let position = invocation.yx;
    @if(horizontal) let direction = vec2<i32>(1, 0);
    @if(!horizontal) let direction = vec2<i32>(0, 1);
    let dimensions = vec2<u32>(width, height);
    let field_size = width * height;
    if (any(position >= dimensions)) { return; }
    var weight = 0.0;
    var reference = vec2<f32>(0.0);
    var mean_offset = vec2<f32>(0.0);
    var products = vec3<f32>(0.0);
    for (var offset = -radius; offset <= radius; offset++) {
        var moments: Moments;
        let sample = clamp_position(vec2<i32>(position) + direction * offset, dimensions);
        let sample_index = sample.y * width + sample.x;
        @if(horizontal) {
            let means = vec2<f32>(channels[field_size + sample_index], channels[2u * field_size + sample_index]);
            moments = Moments(means, select(0.0, 1.0, channels[sample_index] <= maximum_brightfield), vec3<f32>(0.0));
        }
        @if(!horizontal) { moments = partials[sample_index]; }
        let sample_weight = weights[u32(offset + radius)] * moments.weight;
        if (sample_weight <= 0.0) { continue; }
        if (weight == 0.0) { reference = moments.means; }
        let difference = moments.means - reference - mean_offset;
        let combined_weight = weight + sample_weight;
        let fraction = sample_weight / combined_weight;
        products += sample_weight * moments.products
                  + weight * fraction * vec3<f32>(difference * difference, difference.x * difference.y);
        mean_offset += fraction * difference;
        weight = combined_weight;
    }
    let index = position.y * width + position.x;
    products /= max(weight, 1e-30);
    @if(horizontal) { output[index] = Moments(reference + mean_offset, weight, products); }
    @if(!horizontal) {
        output[index] = vec2<f32>(0.0);
        if (weight > 1e-6 && channels[index] <= maximum_brightfield) {
            output[index] = correlation(products);
        }
    }
}
