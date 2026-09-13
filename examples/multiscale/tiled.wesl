import package::imaging::indexing::linear_index;
import package::multiscale::boundary::clamp_position;
import package::multiscale::convolution::{source, direction};
import package::multiscale::coefficients::{radius, weights};

var<workgroup> tile: array<f32, 64 + 2 * radius>;

fn convolve_tiled(position: vec3<u32>, dimensions: vec2<u32>, local_index: u32) -> f32 {
    let origin = vec2<i32>(position.xy) - direction() * i32(local_index);
    for (var index = local_index; index < 64u + 2u * u32(radius); index += 64u) {
        let sample = clamp_position(origin + direction() * (i32(index) - radius), dimensions);
        tile[index] = source[linear_index(vec3<u32>(sample, position.z), dimensions)];
    }
    workgroupBarrier();
    var value = 0.0;
    for (var index = 0u; index < 2u * u32(radius) + 1u; index++) {
        value += weights[index] * tile[local_index + index];
    }
    return value;
}
