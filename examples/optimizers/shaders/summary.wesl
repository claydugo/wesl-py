import package::examples::imaging::reduction::sum_workgroup;

struct Progress {
    frame: u32,
    step: u32,
}

@group(0) @binding(0) var<storage, read> scores: array<vec2f>;
@group(0) @binding(1) var<storage, read_write> history: array<vec4f>;
@group(0) @binding(2) var<uniform> progress: Progress;

@compute @workgroup_size(256)
fn main(@builtin(local_invocation_index) lane: u32) {
    var total = vec4f(0.0);
    for (var index = lane; index < arrayLength(&scores); index += 256u) {
        total += vec4f(scores[index], 0.0, 0.0);
    }
    let sum = sum_workgroup(total, lane);
    if (lane == 0u) {
        history[progress.frame % arrayLength(&history)] = vec4f(
            sum.xy / f32(arrayLength(&scores)),
            f32(progress.step),
            1.0,
        );
    }
}
