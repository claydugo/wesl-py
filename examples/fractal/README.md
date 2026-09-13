# Fractal compute shader

```bash
pixi run -e fractal python -m examples.fractal --output /tmp/fractals --show
```

The command requires an explicit `--output` directory.
It saves `mandelbrot.png` and `julia.png` there and opens them in a browser.
Omit `--show` to save the images without opening a window.
Each image contains 640 by 480 pixels.
The `fractal` environment provides wgpu-py, imageio, and NumPy.
These dependencies also form the optional `fractal` extra.

Each GPU invocation computes one pixel.
Both fractals iterate the same equation, `value = value² + constant`.
Mandelbrot starts at zero and uses the pixel coordinate as the constant.
Julia starts at the pixel coordinate and uses a fixed constant.
The escape iteration controls the color.
Points that remain bounded for 256 iterations appear dark.

Start with [quadratic.wesl](quadratic.wesl) to read the equation and escape test.
Then read [render.wesl](render.wesl) to see how each pixel uses that result:

```wgsl
import package::fractal::quadratic::escape;
import package::fractal::palette::color;
```

The pixel color comes from `color(escape(point))`.
The equation and palette have no buffer bindings or pixel coordinates.

| File | Role |
| --- | --- |
| `render.wesl` | Map pixels to coordinates and write packed colors. |
| `quadratic.wesl` | Iterate the equation and calculate a smooth escape value. |
| `palette.wesl` | Map escape values to RGB colors. |
| `__main__.py` | Compile two variants, dispatch them, and save their output. |

`render.wesl` imports the iteration and palette functions.
Python sets `features={"julia": ...}` when it compiles each variant.
The `@if` declarations select the starting value and constant during compilation.
The generated WGSL contains one variant and the same iteration loop.
The palette stays separate from the fractal calculation.

wgpu-py handles buffers, bindings, dispatch, and readback through
`compute_with_buffers`. NumPy views the returned bytes as an image array.
Imageio saves the array as PNG.

Change the Julia constant `(-0.8, 0.156)` in `quadratic.wesl` to change its shape.
Change `palette.wesl` to recolor both fractals without changing their iteration.
Change `width, height` in `__main__.py` to render at another resolution.
The dispatch rounds up to cover partial workgroups.

This example introduces imports and conditional compilation.
The [multiscale example](../multiscale/README.md) uses them to share convolution
code across filter directions, scales, and memory implementations.
