import package::examples::compaction::predicate::selected;

@group(0) @binding(0) var<storage, read> values: array<u32>;
@group(0) @binding(1) var<storage, read> prefixes: array<u32>;
@group(0) @binding(2) var<storage, read_write> output: array<u32>;

@compute @workgroup_size(128)
fn main(@builtin(global_invocation_id) index: vec3u) {
    if (index.x < arrayLength(&values)) {
        let value = values[index.x];
        if (selected(value)) {
            output[prefixes[index.x]] = value;
        }
    }
}
