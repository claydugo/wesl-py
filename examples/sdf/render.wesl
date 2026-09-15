import package::sdf::camera::project;
import package::sdf::parameters::parameters;
import package::sdf::scene::distance_to_scene;
import package::sdf::surface::normal;

struct FragmentOutput {
    @location(0) color: vec4<f32>,
    @builtin(frag_depth) depth: f32,
}

@vertex
fn vertex_main(@builtin(vertex_index) index: u32) -> @builtin(position) vec4<f32> {
    let corner = vec2<f32>(f32((index << 1u) & 2u), f32(index & 2u));
    return vec4<f32>(corner * 2.0 - 1.0, 0.0, 1.0);
}

@fragment
fn fragment_main(@builtin(position) pixel: vec4<f32>) -> FragmentOutput {
    let coordinate = (pixel.xy / parameters.viewport.xy * 2.0 - 1.0) * vec2<f32>(1.0, -1.0);
    let direction = normalize(
        parameters.camera_forward.xyz + 0.57735027 * (
            parameters.camera_right.xyz * coordinate.x * parameters.viewport.x / parameters.viewport.y +
            parameters.camera_up.xyz * coordinate.y
        )
    );
    let background = mix(vec3<f32>(0.035, 0.05, 0.08), vec3<f32>(0.1, 0.15, 0.2),
        clamp(0.5 + direction.y, 0.0, 1.0));
    var travel = 0.1;
    var hit = false;
    for (var step = 0u; step < 128u; step += 1u) {
        let distance = distance_to_scene(parameters.camera_position.xyz + direction * travel);
        if (distance < 0.001) { hit = true; break; }
        travel += distance;
        if (travel > 40.0) { break; }
    }
    var output: FragmentOutput;
    output.color = vec4<f32>(background, 1.0);
    output.depth = 1.0;
    if (!hit) { return output; }
    let position = parameters.camera_position.xyz + direction * travel;
    let surface_normal = normal(position);
    let light = normalize(vec3<f32>(-3.0, 6.0, 4.0) - position);
    var shadow = 1.0;
    var shadow_travel = 0.035;
    for (var step = 0u; step < 32u; step += 1u) {
        let distance = distance_to_scene(position + surface_normal * 0.01 + light * shadow_travel);
        shadow = min(shadow, 12.0 * distance / shadow_travel);
        shadow_travel += clamp(distance, 0.025, 0.3);
        if (distance < 0.001 || shadow_travel > 5.0) { break; }
    }
    var material = mix(vec3<f32>(0.025, 0.3, 0.36), vec3<f32>(0.12, 0.65, 0.56),
        clamp(position.y * 0.35 + 0.4, 0.0, 1.0));
    if (position.y < -1.24) {
        let grid = abs(fract(position.xz) - 0.5);
        let line = smoothstep(0.475, 0.495, max(grid.x, grid.y));
        material = mix(vec3<f32>(0.12, 0.15, 0.19), vec3<f32>(0.2, 0.25, 0.29), line);
    }
    let diffuse = max(dot(surface_normal, light), 0.0) * clamp(shadow, 0.15, 1.0);
    let specular = pow(max(dot(surface_normal, normalize(light - direction)), 0.0), 48.0);
    let color = material * (0.3 + diffuse * 0.9) + vec3<f32>(specular * 0.25 * shadow);
    output.color = vec4<f32>(mix(color, background, 1.0 - exp(-0.025 * travel)), 1.0);
    let projected = project(position);
    output.depth = projected.z / projected.w;
    return output;
}
