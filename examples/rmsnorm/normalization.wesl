@id(0) override width: u32;
@id(1) override epsilon: f32 = 0.000001;

public fn scale(square_sum: f32) -> f32 {
    return scale_row(square_sum, width, epsilon);
}

public fn scale_row(square_sum: f32, row_width: u32, row_epsilon: f32) -> f32 {
    return inverseSqrt(square_sum / f32(row_width) + row_epsilon);
}
