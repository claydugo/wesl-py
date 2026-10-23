# FP16 convolution and pooling

Run from the repository root:

```bash
pixi run -e gpu python -m examples.convolution --adapter NVIDIA
```

The example uses wgpu-py and needs `shader-f16`.
`--adapter` selects the first Vulkan adapter whose device name contains the
supplied text. Without it, wgpu-py selects a high-performance adapter.
It creates synthetic inputs and verifies convolution and pooling with NumPy.

The example reuses compute pipelines and resources across three inputs.
`wesl.testing.run_test()` compares the outputs with NumPy references on the GPU.

The reusable shaders live in [shaders](shaders).

Convolution writes binding 0. Bindings 1 through 4 contain channel segments.
Bindings 5 and 6 contain OIHW weights and per-channel bias.
Bind unused input slots to the first input buffer and set their channel counts
to zero. The fourth channel count is the total minus the first three counts.

Convolution override IDs 0 through 10 are input height, input width, input
channels, output channels, kernel size, stride, padding, activation mode, and
the first three segment channel counts. IDs 11 and 12 select wider products and
wider bias/activation arithmetic. Both default to false. All accumulation uses
FP32. Storage remains FP16.

Activation modes are 0 for linear, 1 for leaky ReLU with slope 0.1, and 2 for
sigmoid. Mode 2 writes six attributes per pixel and anchor.

`tiled` handles square kernels. Its workgroup covers 32 positions and 16 output
channels. `direct` requires a 3 by 3 kernel. Its workgroup covers 128 runs of
three adjacent output pixels and four output channels. `pointwise` requires a
1 by 1 kernel. Its workgroup covers 512 positions and four output channels.
All entry points handle incomplete channel and pixel tiles.

Pooling uses bindings 0 and 1 for output and input. Its override IDs 0 through
5 are height, width, channels, kernel size, stride, and padding. Resize uses the
same bindings, with IDs 0 through 3 for height, width, channels, and scale.
Both use 256 invocations per workgroup.

## Shader tests

```bash
pixi run -e testing python -m pytest tests/examples/convolution -q
pixi run -e testing python -m pytest tests/examples/convolution \
  --convolution-adapter AMD -q
```

The resource fixture dispatches the kernel and retains its buffers while a
native WESL test compares outputs with NumPy.

The cases cover padding, stride, partial tiles, uneven input segments, negative
pooling inputs, and output guards. Each case selects one arithmetic policy
through override IDs 11 and 12.

FP16 arithmetic can vary across devices. Tolerances cover the NumPy reference;
they do not establish equivalent predictions after discontinuous operations
such as non-maximum suppression.
