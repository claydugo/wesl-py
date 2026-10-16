public fn key(value: u32) -> u32 {
    let color = unpack4x8unorm(value).rgb;
    return u32(round(dot(color, vec3f(0.2126, 0.7152, 0.0722)) * 1023.0));
}
