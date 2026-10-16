def create_layout(width: int) -> dict[str, int]:
    return {
        "width": width,
        "first_weights": 0,
        "first_biases": 2 * width,
        "second_weights": 3 * width,
        "second_biases": 3 * width + width * width,
        "output_weights": 4 * width + width * width,
        "output_bias": 5 * width + width * width,
        "parameter_count": 5 * width + width * width + 1,
    }
