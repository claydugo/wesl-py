import wesl
from wgpu.utils.compute import compute_with_buffers

modules = {
    "package::main": """
        import package::settings::value;
        @group(0) @binding(0)
        var<storage, read_write> output: array<u32>;
        @compute @workgroup_size(1)
        fn main() { output[0] = value(); }
    """,
    "package::settings": """
        @if(enabled) fn value() -> u32 { return 7u; }
        @if(!enabled) fn value() -> u32 { return 3u; }
    """,
}

for enabled, expected in ((False, 3), (True, 7)):
    wgsl = wesl.compile(
        modules,
        options=wesl.CompileOptions(features=wesl.Features(flags={"enabled": enabled})),
    ).wgsl
    output = compute_with_buffers({}, {0: (1, "I")}, wgsl, n=1)
    assert output[0][0] == expected
