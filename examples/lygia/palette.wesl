fn color(elevation: f32, water_level: f32, palette: u32) -> vec3f {
    let depth = clamp((water_level - elevation) / 0.3, 0.0, 1.0);
    let height = clamp((elevation - water_level) / (1.0 - water_level), 0.0, 1.0);
    var ocean = mix(vec3f(0.018, 0.045, 0.075), vec3f(0.06, 0.31, 0.34), pow(1.0 - depth, 1.6));
    var land = mix(vec3f(0.19, 0.30, 0.27), vec3f(0.48, 0.53, 0.39), smoothstep(0.02, 0.35, height));
    land = mix(land, vec3f(0.91, 0.88, 0.76), smoothstep(0.25, 0.7, height));
    land = mix(vec3f(0.83, 0.80, 0.66), land, smoothstep(0.0, 0.025, height));
    if (palette == 1u) {
        ocean = mix(vec3f(0.055, 0.07, 0.09), vec3f(0.22, 0.28, 0.29), pow(1.0 - depth, 2.0));
        land = mix(vec3f(0.56, 0.27, 0.13), vec3f(0.95, 0.86, 0.67), smoothstep(0.0, 0.8, height));
    }
    if (palette == 2u) {
        ocean = mix(vec3f(0.075, 0.10, 0.12), vec3f(0.22, 0.27, 0.29), 1.0 - depth);
        land = mix(vec3f(0.58, 0.61, 0.59), vec3f(0.93, 0.92, 0.86), smoothstep(0.0, 0.7, height));
    }
    return select(ocean, land, elevation >= water_level);
}
