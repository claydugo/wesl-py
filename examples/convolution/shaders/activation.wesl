enable f16;

@id(12) override wide_activation: bool = false;

fn activate(total: f32, bias: f16, mode: u32) -> f16 {
    if (wide_activation) {
        let value = total + f32(bias);
        if (mode == 1u) {
            return f16(select(value, 0.1 * value, value < 0.0));
        }
        if (mode == 2u) {
            return f16(1.0 / (1.0 + exp(-value)));
        }
        return f16(value);
    }
    let value = f16(total) + bias;
    if (mode == 1u) {
        return select(value, 0.1h * value, value < 0.0h);
    }
    if (mode == 2u) {
        return 1.0h / (1.0h + exp2(value * -1.4423828125h));
    }
    return value;
}
