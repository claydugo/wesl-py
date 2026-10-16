var<workgroup> partial: array<u32, 128>;

struct Scan {
    exclusive: u32,
    total: u32,
}

public fn scan_workgroup(value: u32, lane: u32) -> Scan {
    partial[lane] = value;
    workgroupBarrier();
    for (var stride = 1u; stride < 128u; stride *= 2u) {
        var preceding = 0u;
        if (lane >= stride) {
            preceding = partial[lane - stride];
        }
        workgroupBarrier();
        partial[lane] += preceding;
        workgroupBarrier();
    }
    let result = Scan(partial[lane] - value, partial[127]);
    workgroupBarrier();
    return result;
}
