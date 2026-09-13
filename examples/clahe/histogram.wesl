import package::imaging::indexing::linear_index;

override width: u32;
override height: u32;
override tile_size: u32 = 64u;
@group(0) @binding(0) var<storage, read> source: array<f32>;
@group(0) @binding(1) var<storage, read_write> histograms: array<u32>;
var<workgroup> histogram: array<atomic<u32>, 256>;

@compute @workgroup_size(256)
fn main(@builtin(workgroup_id) tile: vec3<u32>,
        @builtin(local_invocation_index) index: u32) {
    atomicStore(&histogram[index], 0u);
    workgroupBarrier();
    let dimensions = vec2<u32>(width, height);
    for (var sample = index; sample < tile_size * tile_size; sample += 256u) {
        let offset = vec2<u32>(sample % tile_size, sample / tile_size);
        let position = min(tile.xy * tile_size + offset, dimensions - 1u);
        let value = source[linear_index(vec3<u32>(position, tile.z), dimensions)];
        atomicAdd(&histogram[u32(round(clamp(value, 0.0, 1.0) * 255.0))], 1u);
    }
    workgroupBarrier();
    let tile_count = (dimensions + tile_size - 1u) / tile_size;
    histograms[linear_index(tile, tile_count) * 256u + index] = atomicLoad(&histogram[index]);
}
