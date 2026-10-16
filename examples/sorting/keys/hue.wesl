public fn key(value: u32) -> u32 {
    let color = unpack4x8unorm(value).rgb;
    let maximum = max(color.r, max(color.g, color.b));
    let range = maximum - min(color.r, min(color.g, color.b));
    if (range == 0.0) {
        return 0u;
    }
    var hue = (color.g - color.b) / range;
    if (maximum == color.g) {
        hue = 2.0 + (color.b - color.r) / range;
    } else if (maximum == color.b) {
        hue = 4.0 + (color.r - color.g) / range;
    }
    return u32(fract(hue / 6.0 + 1.0) * 1023.0);
}
