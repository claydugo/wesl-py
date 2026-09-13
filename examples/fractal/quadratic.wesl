fn escape(point: vec2<f32>) -> f32 {
    @if(julia) let constant = vec2<f32>(-0.8, 0.156);
    @if(!julia) let constant = point;
    @if(julia) var value = point;
    @if(!julia) var value = vec2<f32>(0.0);
    for (var iteration = 0u; iteration < 256u; iteration++) {
        value = vec2<f32>(value.x * value.x - value.y * value.y, 2.0 * value.x * value.y)
              + constant;
        let squared_radius = dot(value, value);
        if (squared_radius > 256.0) {
            return f32(iteration) + 1.0 - log2(0.5 * log(squared_radius));
        }
    }
    return -1.0;
}
