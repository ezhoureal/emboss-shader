# Dynamic Emboss Height Shader

This repository contains a small WebGL demo for rendering a dynamic embossed
wall ornament from a baked height map. Pointer movement raises the relief around
the cursor while preserving the flat paper/background areas.

## Contents

- `index.html` - Browser demo with the WebGL shader, pointer interaction, and
  height/radius controls.
- `dynamic-emboss.frag` - Standalone fragment shader version of the emboss
  effect for shader tooling and experiments.
- `baroque_wall.glb` - Source GLB model used to bake the relief maps.
- `emboss.jpg` - Reference image.
- `generated/` - Baked runtime textures used by the demo:
  - `baroque_height.png` encodes relief height.
  - `baroque_mask.png` masks ornament coverage.
  - `baroque_normal.png` stores a baked normal preview.
  - `baroque_reference_2d.png` stores a shaded 2D reference render.
  - `baroque_bake_metadata.json` records bake settings and model bounds.
- `tools/bake_glb_height.py` - Projects the GLB mesh to a height map and writes
  the generated textures.
- `tools/extract_glb_images.py` - Extracts embedded images from a GLB for asset
  inspection.

Temporary render/debug output is intentionally ignored by Git. See
`.gitignore` for the current prune list.

## Running The Demo

Serve the repository root with any local HTTP server, then open `index.html`.
Loading the file directly may block the generated textures in some browsers.

```sh
python3 -m http.server 8000
```

Then visit:

```text
http://localhost:8000/
```

Move the pointer over the canvas to raise the embossed relief. Use the controls
in the top-left panel to tune height and radius.

## Regenerating Assets

The bake script expects `ffmpeg` to be available for converting temporary
PGM/PPM files to PNG.

```sh
python3 tools/bake_glb_height.py baroque_wall.glb generated 1024
```

The command rewrites the generated height, mask, normal, reference, and metadata
files. Intermediate `generated/*.pgm` and `generated/*.ppm` files are ignored.

To inspect images embedded in the GLB:

```sh
python3 tools/extract_glb_images.py baroque_wall.glb generated/glb_images
```

Extracted images are ignored because they are inspection artifacts, not runtime
inputs for the demo.

## Validation

For the Python tools:

```sh
python3 -m py_compile tools/bake_glb_height.py tools/extract_glb_images.py
```
