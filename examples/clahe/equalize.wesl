override tile_size: u32 = 64u;
override clip_limit: f32 = 2.0;
@group(0) @binding(0) var<storage, read> histograms: array<u32>;
@group(0) @binding(1) var<storage, read_write> lookup_tables: array<f32>;
var<workgroup> totals: array<u32, 256>;

@compute @workgroup_size(256)
fn main(@builtin(workgroup_id) tile: vec3<u32>,
        @builtin(local_invocation_index) index: u32) {
    let count = histograms[tile.x * 256u + index];
    let limit = max(1u, u32(clip_limit * f32(tile_size * tile_size) / 256.0));
    let clipped = min(count, limit);
    totals[index] = count - clipped;
    workgroupBarrier();
    for (var stride = 128u; stride > 0u; stride /= 2u) {
        if (index < stride) {
            totals[index] += totals[index + stride];
        }
        workgroupBarrier();
    }
    let excess = totals[0];
    let remainder = excess % 256u;
    let spacing = 256u / max(remainder, 1u);
    let residual = select(0u, 1u, index % spacing == 0u && index / spacing < remainder);
    workgroupBarrier();
    totals[index] = clipped + excess / 256u + residual;
    workgroupBarrier();
    for (var distance = 1u; distance < 256u; distance *= 2u) {
        var previous = 0u;
        if (index >= distance) {
            previous = totals[index - distance];
        }
        workgroupBarrier();
        totals[index] += previous;
        workgroupBarrier();
    }
    lookup_tables[tile.x * 256u + index] = f32(totals[index]) / f32(tile_size * tile_size);
}
