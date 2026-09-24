override width: u32;
override height: u32;

struct DisplayParameters {
    center: vec2<f32>,
    radius: f32,
    opacity: f32,
    spacing: f32,
}

@group(0) @binding(0) var<storage, read> values: array<vec2<f32>>;
@group(0) @binding(1) var original: texture_2d<f32>;
@group(0) @binding(2) var output: texture_storage_2d<rgba8unorm, write>;
@group(0) @binding(3) var<uniform> parameters: DisplayParameters;

@compute @workgroup_size(16, 16)
fn polar_guide(@builtin(global_invocation_id) position: vec3<u32>) {
    if (any(position.xy >= vec2<u32>(width, height))) { return; }
    var color = textureLoad(original, vec2<i32>(position.xy), 0).rgb;
    let pixel = vec2<f32>(position.xy);
    let center = parameters.center;
    let displacement = abs(pixel - center);
    let cross = (displacement.x < 1.0 && displacement.y < 8.0)
             || (displacement.y < 1.0 && displacement.x < 8.0);
    let ring = abs(distance(pixel, center) - parameters.radius) < 1.0;
    if (cross || ring) {
        color = vec3<f32>(1.0, 0.85, 0.2);
    }
    textureStore(output, position.xy, vec4<f32>(color, 1.0));
}

@compute @workgroup_size(16, 16)
fn correlation_overlay(@builtin(global_invocation_id) position: vec3<u32>) {
    if (any(position.xy >= vec2<u32>(width, height))) { return; }
    let base = textureLoad(original, vec2<i32>(position.xy), 0).rgb;
    let value = values[position.y * width + position.x];
    let opacity = parameters.opacity * value.y;
    var color = mix(vec3<f32>(0.15, 0.65, 1.0), vec3<f32>(0.92), clamp(value.x + 1.0, 0.0, 1.0));
    color = mix(color, vec3<f32>(1.0, 0.3, 0.1), max(value.x, 0.0));
    textureStore(output, position.xy, vec4<f32>(mix(base, color, opacity), 1.0));
}

@compute @workgroup_size(16, 16)
fn distance_overlay(@builtin(global_invocation_id) position: vec3<u32>) {
    if (any(position.xy >= vec2<u32>(width, height))) { return; }
    let base = textureLoad(original, vec2<i32>(position.xy), 0).rgb;
    let value = values[position.y * width + position.x];
    let opacity = parameters.opacity * value.y;
    let spacing = parameters.spacing;
    var color = mix(vec3<f32>(0.08, 0.35, 0.6), vec3<f32>(1.0, 0.8, 0.2), exp(-0.5 * value.x / spacing));
    let contour = 1.0 - smoothstep(0.0, 1.0, abs(value.x - spacing * round(value.x / spacing)));
    color = mix(color, vec3<f32>(1.0), contour);
    textureStore(output, position.xy, vec4<f32>(mix(base, color, opacity), 1.0));
}
