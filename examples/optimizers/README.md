# Optimizer comparison

Run from the repository root:

```bash
pixi run -e examples python -m examples.optimizers
```

Three copies of one small network learn the same two-class dataset.
Each copy starts from the same weights and uses a different optimizer:
gradient descent, momentum, or Adam.

The background shows the predicted class at every pixel.
The white line is the decision boundary.
White rings mark misclassified training points.
The plot above each panel shows the training loss on a log scale from
`10^-4` to 1. The panel also shows the first step at which every point is correct.

Use the controls to choose a dataset, the training speed, the learning rates,
and the decay rates. Pause and Step advance one step at a time.
Reset weights draws a new initialization for all three copies.

## Edit the shaders live

Edit any shader file that the example compiles while it runs.
The example checks the files four times per second.
When one changes, it rebuilds every pipeline and resets the weights.

For example, change `activate` in [network.wesl](network.wesl) to `max(value, 0.0)`.
Then change `slope` to `select(0.0, 1.0, value > 0.0)`.
All three panels retrain with ReLU units.
The panel shows WESL diagnostics with the file, line, and column.
WebGPU reports type errors against the generated WGSL.
The previous pipelines continue to run until the next successful build.

The example watches the files in `CompileResult.sources`, so it watches each
imported module, including the substituted rules. After a failed build, it also
watches each file that a diagnostic names, such as a new module with an error.

## Why WESL

[network.wesl](network.wesl) defines the forward pass, the loss, and the
parameter index functions. The network has two hidden layers and one logit
output. Training and display import the same network:

- [gradients.wesl](shaders/gradients.wesl) calls [backward.wesl](backward.wesl)
  for each sample in a compute shader.
- [boundary.wesl](shaders/boundary.wesl) evaluates the network at every pixel
  in a fragment shader.
- [points.wesl](shaders/points.wesl) marks misclassified points in a vertex
  shader.

The panels show the model that the GPU trains. No weights return to Python.

[update.wesl](shaders/update.wesl) averages the gradients and imports
`package::examples::optimizers::rule::update`. No file has that path.
[renderer.py](renderer.py) supplies one file from [rules](rules) as that module
for each panel. The rule modules declare their decay rates as overrides with
numeric IDs. Python passes the slider values as pipeline constants.
A slider change creates new update pipelines from the compiled shader modules.
It does not compile again, and it keeps the weights.

[layout.py](layout.py) computes the parameter offsets for a hidden width.
[renderer.py](renderer.py) passes them as `constants`. The shaders import
them from the virtual module `constants`.
The width sizes private arrays, so it must be a compile-time constant.
[viewer.py](viewer.py) uses the same offsets to initialize the weights.

[summary.wesl](shaders/summary.wesl) reduces the loss and accuracy on the GPU
with `sum_workgroup` from the [imaging library](../imaging/README.md).
It writes one entry per frame into a ring buffer.
Python reads the ring buffer every 15 frames for the plots.

[network.wesl](network.wesl) reads weights through `parameter` from
[parameters.wesl](parameters.wesl). The native test substitutes this module.
[plane.wesl](plane.wesl) shares the visible extent between the two renderers.

## Verify

```bash
pixi run -e testing python -m pytest tests/examples/test_optimizers.py \
  tests/examples/optimizers -q
```

The Python test reads the GPU gradients for three steps. It applies each update
rule in NumPy and compares the result with the GPU weights. It then trains in the
offscreen viewer and checks that Adam fits every point and has a lower loss than
gradient descent.

[The native test](../../tests/examples/optimizers/gradients.test.wesl) checks
`backward` against central finite differences of the loss for four samples.
Its fixtures substitute [perturbed.wesl](../../tests/examples/optimizers/perturbed.wesl)
for the parameters module. That module adds a perturbation to one weight.
Run this test after you change `activate` and `slope`.
