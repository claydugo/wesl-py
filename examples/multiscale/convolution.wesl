import super::super::imaging::indexing::linear_index;
import super::boundary::clamp_position;
import super::coefficients::{radius, weights};

@group(0) @binding(0) var<storage, read> source: array<f32>;

fn direction() -> vec2<i32> {
    @if(horizontal) { return vec2<i32>(1, 0); }
    @if(!horizontal) { return vec2<i32>(0, 1); }
}

fn convolve(position: vec3<u32>, dimensions: vec2<u32>) -> f32 {
    var value = 0.0;
    for (var offset = -radius; offset <= radius; offset++) {
        let sample = clamp_position(vec2<i32>(position.xy) + direction() * offset, dimensions);
        value += weights[u32(offset + radius)]
               * source[linear_index(vec3<u32>(sample, position.z), dimensions)];
    }
    return value;
}
