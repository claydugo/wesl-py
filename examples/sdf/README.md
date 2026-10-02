# SDF playground

Run from the repository root:

```bash
pixi run -e examples python -m examples.sdf
```

Particles fall onto four blended spheres or through the optional tunnel.

Drag the scene to orbit. Scroll to zoom.
Use the controls to separate the spheres, change their blend, or cut a tunnel.
The surface and particle collisions respond to the same changes.

## Why WESL

[scene.wesl](scene.wesl) defines the distance to the surface.
It imports sphere and smooth-union functions from [primitives.wesl](primitives.wesl).
[surface.wesl](surface.wesl) samples that distance to calculate a normal.

Two shaders import the same geometry:

- [render.wesl](shaders/render.wesl) traces rays in a fragment shader.
- [simulate.wesl](shaders/simulate.wesl) moves particles in a compute shader.

Both import `distance_to_scene` and `normal`, so scene edits change rendering
and collisions together.

[renderer.py](renderer.py) compiles the pipelines and submits GPU passes.
[viewer.py](viewer.py) manages camera input and controls.

The tunnel uses `@if(cutout)` in the shared scene module.
Python compiles both variants for rendering and simulation at startup.
The checkbox selects the corresponding pair of pipelines.
The variant without a tunnel excludes its distance calculation.
Blend, separation, tunnel radius, and physics controls use uniforms.

[camera.wesl](camera.wesl) also supplies one projection function for the surface
and particle renderers. Both write depth so particles can pass behind the surface
and through the tunnel.

Simulation and rendering share a GPU particle buffer.
The simulation uses four substeps and projects penetrating particles onto the
surface. Particles do not collide with each other.

## Verify

```bash
pixi run -e testing python -m pytest tests/examples/test_sdf.py -q
```

The tests verify floor collisions and passage through the tunnel.
They render both variants offscreen and exercise resizing and particle reset.
