@id(0) override width: u32;
@id(1) override epsilon: f32 = 0.000001;

fn scale(square_sum: f32) -> f32 {
    return inverseSqrt(square_sum / f32(width) + epsilon);
}
