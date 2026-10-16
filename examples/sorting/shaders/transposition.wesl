import package::examples::sorting::order::ordered;

@group(0) @binding(0) var<storage, read_write> values: array<u32>;
@group(0) @binding(1) var<storage, read_write> marks: array<u32>;
@group(0) @binding(2) var<uniform> parity: u32;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) index: vec3u) {
    let left = 2u * index.x + parity;
    if (left + 1u >= arrayLength(&values)) {
        return;
    }
    let first = values[left];
    let second = values[left + 1u];
    if (!ordered(first, second)) {
        values[left] = second;
        values[left + 1u] = first;
        marks[left] = 1u;
        marks[left + 1u] = 1u;
    }
}
