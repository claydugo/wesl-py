import package::lygia::terrain::elevation;
import package::lygia::palette::color;

struct Parameters {
    viewport: vec2f,
    time: f32,
    seed: i32,
    field: vec4f,
    style: vec4f,
}

@group(0) @binding(0) var<uniform> parameters: Parameters;

@vertex
fn vertex_main(@builtin(vertex_index) index: u32) -> @builtin(position) vec4f {
    let corner = vec2f(f32((index << 1u) & 2u), f32(index & 2u));
    return vec4f(corner * 2.0 - 1.0, 0.0, 1.0);
}

@fragment
fn fragment_main(@builtin(position) pixel: vec4f) -> @location(0) vec4f {
    let position = (pixel.xy - parameters.viewport * 0.5) / parameters.viewport.y
        * parameters.field.z + parameters.field.xy;
    let height = elevation(position, parameters.time, parameters.seed, parameters.field.w);
    let water_level = parameters.style.x;
    let gradient = vec2f(dpdx(height), dpdy(height)) * parameters.viewport.y / parameters.field.z;
    let normal = normalize(vec3f(-gradient * 0.65, 1.0));
    let light = normalize(vec3f(-0.6, -0.8, 1.3));
    let lighting = 0.58 + 0.58 * max(dot(normal, light), 0.0);
    let land = smoothstep(water_level, water_level + 0.015, height);
    var shaded = color(height, water_level, u32(parameters.style.y));
    shaded *= mix(1.0, lighting, land * parameters.style.w);
    let level = (height - water_level) * 32.0;
    let pixel_width = max(fwidth(level), 0.0001);
    let contour = (1.0 - smoothstep(pixel_width * 0.25, pixel_width * 0.9, abs(fract(level + 0.5) - 0.5)))
        * (1.0 - smoothstep(0.35, 0.9, pixel_width));
    let major_width = max(fwidth(level * 0.25), 0.0001);
    let major = 1.0 - smoothstep(major_width * 0.4, major_width, abs(fract(level * 0.25 + 0.5) - 0.5));
    let ink = mix(vec3f(0.27, 0.53, 0.56), vec3f(0.10, 0.15, 0.13), land);
    shaded = mix(shaded, ink, (0.22 * contour + 0.16 * major) * parameters.style.z);
    let coast = 1.0 - smoothstep(0.0, max(fwidth(height), 0.0001) * 1.2, abs(height - water_level));
    shaded = mix(shaded, vec3f(0.87, 0.84, 0.69), coast * 0.3);
    shaded = clamp(shaded, vec3f(0.0), vec3f(1.0));
    @if(srgb_target) {
        shaded = select(pow((shaded + 0.055) / 1.055, vec3f(2.4)), shaded / 12.92, shaded <= vec3f(0.04045));
    }
    return vec4f(shaded, 1.0);
}
