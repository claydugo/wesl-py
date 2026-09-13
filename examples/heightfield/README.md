# Height to surface

```bash
pixi run -e compute python -m examples.heightfield --output /tmp/heightfield --show
```

The example requires an explicit `--output` directory.
It saves a synthetic height field, its edges, and its normals as PNG images there.
It also saves a relighting GIF with 36 frames computed on the GPU.
On Linux, `--show` opens the GIF in the desktop image viewer with `xdg-open`.
Omit `--show` to generate the files only.
The example uses wgpu-py, NumPy, and imageio.

Start with [surface.wesl](surface.wesl).
One gradient supplies the edge magnitude and the surface normal.
[render.wesl](render.wesl) uses those operations directly:

```wgsl
@if(edges) let color = vec3<f32>(1.0 - exp(-length(gradient(position, dimensions))));
@if(normals) let color = 0.5 + 0.5 * normal(position, dimensions);
@if(shaded) let color = illuminate(normal(position, dimensions), vec3<f32>(light_x, light_y, light_z));
```

Python compiles the entry point with `features={mode: True}`.
WESL selects the output during compilation.
The edge shader does not contain the normal or lighting functions.
The normal shader does not contain the lighting function.
Each variant uses one compute pass.

[field.wesl](field.wesl) owns the input buffer and clamps sample coordinates.
[surface.wesl](surface.wesl) calculates the gradient and normal.
[lighting.wesl](lighting.wesl) calculates diffuse light and a specular highlight.
The equations use coordinates from -1 to 1 along each image axis.
The gradient uses central differences and repeats the nearest boundary sample.
Single-row and single-column images have zero slope along their missing axis.

[compute.py](compute.py) compiles a variant, dispatches it, and returns RGBA pixels.
[__main__.py](__main__.py) creates the height field and saves the images.
The animation uses the same heights for each light direction.
The convenience helper creates buffers and a pipeline for each dispatch.
This script demonstrates composition, not sustained rendering performance.

Change the height equation in `__main__.py` to change all three results.
Change the material in `lighting.wesl` to change the shaded result.
Change the sampling policy in `field.wesl` to change boundary handling consistently.

```bash
pixi run -e compute python -m examples.heightfield.verify
```

The reference uses NumPy and checks each color channel within one 8-bit step.
It covers constant fields, ramps, boundary impulses, partial workgroups,
noncontiguous arrays, and light behind the surface.
