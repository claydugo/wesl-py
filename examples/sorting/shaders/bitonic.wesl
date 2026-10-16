import package::examples::sorting::order::ordered;

struct Stage {
    block: u32,
    distance: u32,
}

@group(0) @binding(0) var<storage, read_write> values: array<u32>;
@group(0) @binding(1) var<storage, read_write> marks: array<u32>;
@group(0) @binding(2) var<uniform> stage: Stage;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) index: vec3u) {
    let partner = index.x ^ stage.distance;
    if (index.x >= arrayLength(&values) || partner <= index.x) {
        return;
    }
    let low = values[index.x];
    let high = values[partner];
    let ascending = (index.x & stage.block) == 0u;
    if (select(!ordered(high, low), !ordered(low, high), ascending)) {
        values[index.x] = high;
        values[partner] = low;
        marks[index.x] = 1u;
        marks[partner] = 1u;
    }
}
