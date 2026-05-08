#!/usr/bin/env python3
import json
import struct
import sys
from pathlib import Path


EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


def main():
    glb = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("baroque_wall.glb")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("generated/glb_images")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(glb, "rb") as f:
        _magic, _version, length = struct.unpack("<III", f.read(12))
        doc = None
        bin_chunk = None
        while f.tell() < length:
            chunk_len, chunk_type = struct.unpack("<II", f.read(8))
            data = f.read(chunk_len)
            if chunk_type == 0x4E4F534A:
                doc = json.loads(data.decode("utf-8"))
            elif chunk_type == 0x004E4942:
                bin_chunk = data

    if doc is None or bin_chunk is None:
        raise SystemExit("Invalid GLB")

    for i, image in enumerate(doc.get("images", [])):
        view = doc["bufferViews"][image["bufferView"]]
        offset = view.get("byteOffset", 0)
        length = view["byteLength"]
        name = image.get("name", f"image_{i}")
        suffix = EXTENSIONS.get(image.get("mimeType"), ".bin")
        out_path = out_dir / f"{i}_{name}{suffix}"
        out_path.write_bytes(bin_chunk[offset : offset + length])
        print(out_path)


if __name__ == "__main__":
    main()
