import package::examples::parallel::scan::scan_workgroup;
import package::tests::examples::random::random;
import wgsl_test::expectEq;

fn input(round: u32, lane: u32) -> u32 {
    return u32(random(round * 128u + lane) * 1000.0);
}

@test @workgroup_size(128)
fn exclusive_prefix_and_total(@builtin(local_invocation_index) lane: u32) {
    for (var round = 0u; round < 3u; round++) {
        let scan = scan_workgroup(input(round, lane), lane);
        var exclusive = 0u;
        var total = 0u;
        for (var index = 0u; index < 128u; index++) {
            let value = input(round, index);
            exclusive += select(0u, value, index < lane);
            total += value;
        }
        expectEq(scan.exclusive, exclusive);
        expectEq(scan.total, total);
    }
}
