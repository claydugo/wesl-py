fn illuminate(surface_normal: vec3<f32>, light_direction: vec3<f32>) -> vec3<f32> {
    let light = normalize(light_direction);
    let diffuse = max(dot(surface_normal, light), 0.0);
    let reflected = reflect(-light, surface_normal);
    let highlight = select(0.0, pow(max(reflected.z, 0.0), 12.0), diffuse > 0.0);
    let copper = vec3<f32>(0.55, 0.22, 0.07) * (0.16 + 0.84 * diffuse);
    return pow(copper + vec3<f32>(1.0, 0.85, 0.6) * 0.65 * highlight, vec3<f32>(1.0 / 2.2));
}
