import lygia::color::palette::heatmap::heatmap;
import lygia::math::map::map;

fn colorize(value: f32, minimum: f32, maximum: f32) -> vec4f {
    let fraction = clamp(map(value, minimum, maximum, 0.0, 1.0), 0.0, 1.0);
    return vec4f(clamp(heatmap(fraction), vec3f(0.0), vec3f(1.0)), 1.0);
}
