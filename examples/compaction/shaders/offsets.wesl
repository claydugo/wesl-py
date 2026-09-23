@group(0) @binding(0) var<storage, read_write> prefixes: array<u32>;
@group(0) @binding(1) var<storage, read> parent: array<u32>;

@compute @workgroup_size(128)
fn main(@builtin(global_invocation_id) index: vec3u) {
    if (index.x < arrayLength(&prefixes)) {
        prefixes[index.x] += parent[index.x / 128u];
    }
}
