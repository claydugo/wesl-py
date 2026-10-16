import package::examples::parallel::scan::scan_workgroup;
import package::examples::sorting::key::key;

@group(0) @binding(0) var<storage, read> values: array<u32>;
@group(0) @binding(1) var<storage, read_write> sorted: array<u32>;
@group(0) @binding(2) var<storage, read_write> marks: array<u32>;
@group(0) @binding(3) var<uniform> bit: u32;

@compute @workgroup_size(128)
fn main(@builtin(local_invocation_index) lane: u32) {
    let count = arrayLength(&values);
    var zero_count = 0u;
    for (var start = 0u; start < count; start += 128u) {
        var zero = 0u;
        if (start + lane < count) {
            zero = 1u - ((key(values[start + lane]) >> bit) & 1u);
        }
        zero_count += scan_workgroup(zero, lane).total;
    }
    var offset = 0u;
    for (var start = 0u; start < count; start += 128u) {
        let index = start + lane;
        var zero = 0u;
        if (index < count) {
            zero = 1u - ((key(values[index]) >> bit) & 1u);
        }
        let scan = scan_workgroup(zero, lane);
        let preceding_zeros = offset + scan.exclusive;
        if (index < count) {
            var destination = zero_count + index - preceding_zeros;
            if (zero == 1u) {
                destination = preceding_zeros;
            }
            sorted[destination] = values[index];
            marks[destination] = select(0u, 1u, destination != index);
        }
        offset += scan.total;
    }
}
