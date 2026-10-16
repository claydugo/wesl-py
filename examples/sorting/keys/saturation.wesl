public fn key(value: u32) -> u32 {
    let color = unpack4x8unorm(value).rgb;
    let maximum = max(color.r, max(color.g, color.b));
    if (maximum == 0.0) {
        return 0u;
    }
    let minimum = min(color.r, min(color.g, color.b));
    return u32(round((maximum - minimum) / maximum * 1023.0));
}
