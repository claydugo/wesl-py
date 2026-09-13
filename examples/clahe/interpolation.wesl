import package::imaging::indexing::linear_index;

@group(0) @binding(1) var<storage, read> lookup_tables: array<f32>;

fn lookup(tile: vec2<i32>, channel: u32, value: u32, tile_count: vec2<u32>) -> f32 {
    let position = vec2<u32>(clamp(tile, vec2<i32>(0), vec2<i32>(tile_count) - 1));
    return lookup_tables[linear_index(vec3<u32>(position, channel), tile_count) * 256u + value];
}

fn interpolate(position: vec3<u32>, value: u32, tile_size: u32, tile_count: vec2<u32>) -> f32 {
    let coordinate = vec2<f32>(position.xy % tile_size) / f32(tile_size) - 0.5;
    let lower = vec2<i32>(position.xy / tile_size) + vec2<i32>(floor(coordinate));
    let fraction = fract(coordinate);
    let top = mix(lookup(lower, position.z, value, tile_count),
                  lookup(lower + vec2<i32>(1, 0), position.z, value, tile_count), fraction.x);
    let bottom = mix(lookup(lower + vec2<i32>(0, 1), position.z, value, tile_count),
                     lookup(lower + vec2<i32>(1, 1), position.z, value, tile_count), fraction.x);
    return mix(top, bottom, fraction.y);
}
