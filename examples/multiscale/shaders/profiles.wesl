import package::imaging::coordinates::polar_position;
import package::imaging::reduction::sum_workgroup;

override width: u32;
override height: u32;
override center_x: f32;
override center_y: f32;
override maximum_radius: f32;
override profile_count: u32;
@group(0) @binding(0) var<storage, read> channels: array<f32>;
@group(0) @binding(1) var<storage, read_write> output: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read_write> partials: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read> distances: array<vec2<f32>>;

@compute @workgroup_size(256)
fn radial_profile(@builtin(workgroup_id) group: vec3<u32>, @builtin(local_invocation_index) local_index: u32) {
    let dimensions = vec2<u32>(width, height);
    var total = vec4<f32>(0.0);
    for (var angle = local_index; angle < width; angle += 256u) {
        let sample = polar_position(vec2<u32>(angle, group.x), dimensions, vec2<f32>(center_x, center_y), maximum_radius);
        if (all(sample >= vec2<f32>(0.0)) && all(sample <= vec2<f32>(dimensions - 1u))) {
            let index = group.x * width + angle;
            total += vec4<f32>(channels[width * height + index], channels[2u * width * height + index], 1.0, 0.0);
        }
    }
    total = sum_workgroup(total, local_index);
    if (local_index == 0u) {
        let radius = maximum_radius * f32(group.x) / f32(max(height - 1u, 1u));
        output[group.x] = vec4<f32>(total.xy / max(total.z, 1.0), total.z, radius);
    }
}

@compute @workgroup_size(256)
fn accumulate_distance(@builtin(workgroup_id) group: vec3<u32>, @builtin(local_invocation_index) local_index: u32) {
    let extent = f32((min(width, height) + 1u) / 2u);
    var total = vec4<f32>(0.0);
    for (var index = group.y * 16384u + local_index; index < min((group.y + 1u) * 16384u, width * height); index += 256u) {
        if (distances[index].y == 0.0) { continue; }
        let bin = min(u32(distances[index].x * f32(profile_count) / extent), profile_count - 1u);
        if (bin == group.x) {
            total += vec4<f32>(channels[width * height + index], channels[2u * width * height + index], 1.0, 0.0);
        }
    }
    total = sum_workgroup(total, local_index);
    if (local_index == 0u) {
        partials[group.y * profile_count + group.x] = total;
    }
}

@compute @workgroup_size(256)
fn finalize_distance(@builtin(workgroup_id) group: vec3<u32>, @builtin(local_invocation_index) local_index: u32) {
    let chunk_count = (width * height + 16383u) / 16384u;
    var total = vec4<f32>(0.0);
    for (var chunk = local_index; chunk < chunk_count; chunk += 256u) {
        total += partials[chunk * profile_count + group.x];
    }
    total = sum_workgroup(total, local_index);
    if (local_index == 0u) {
        let extent = f32((min(width, height) + 1u) / 2u);
        let center = (f32(group.x) + 0.5) * extent / f32(profile_count);
        output[group.x] = vec4<f32>(total.xy / max(total.z, 1.0), total.z, center);
    }
}
