#!/usr/bin/env python3
import json
import math
import struct
import subprocess
import sys
from array import array
from pathlib import Path


COMPONENT_SIZES = {
    5120: 1,
    5121: 1,
    5122: 2,
    5123: 2,
    5125: 4,
    5126: 4,
}

TYPE_COUNTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
}


def load_glb(path):
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67 or version != 2:
            raise ValueError("Expected glTF 2.0 GLB")

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
        raise ValueError("GLB is missing JSON or BIN chunk")
    return doc, bin_chunk


def accessor_view(doc, bin_chunk, accessor_index):
    accessor = doc["accessors"][accessor_index]
    view = doc["bufferViews"][accessor["bufferView"]]
    component_type = accessor["componentType"]
    component_size = COMPONENT_SIZES[component_type]
    component_count = TYPE_COUNTS[accessor["type"]]
    count = accessor["count"]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", component_size * component_count)
    return memoryview(bin_chunk), offset, stride, count, component_type, component_count


def read_vec3(view_tuple, index):
    data, offset, stride, _count, component_type, component_count = view_tuple
    if component_type != 5126 or component_count < 3:
        raise ValueError("Expected float VEC3 accessor")
    o = offset + index * stride
    return struct.unpack_from("<fff", data, o)


def read_index(view_tuple, index):
    data, offset, stride, _count, component_type, _component_count = view_tuple
    o = offset + index * stride
    if component_type == 5125:
        return struct.unpack_from("<I", data, o)[0]
    if component_type == 5123:
        return struct.unpack_from("<H", data, o)[0]
    if component_type == 5121:
        return data[o]
    raise ValueError("Unsupported index component type")


def write_pgm(path, values, width, height):
    with open(path, "wb") as f:
        f.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
        f.write(values)


def write_ppm(path, rgb, width, height):
    with open(path, "wb") as f:
        f.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        f.write(rgb)


def ffmpeg_convert(src, dst):
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), str(dst)],
        check=True,
    )


def main():
    glb = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("baroque_wall.glb")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("generated")
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
    out_dir.mkdir(parents=True, exist_ok=True)

    doc, bin_chunk = load_glb(glb)
    primitive = doc["meshes"][0]["primitives"][0]
    positions = accessor_view(doc, bin_chunk, primitive["attributes"]["POSITION"])
    indices = accessor_view(doc, bin_chunk, primitive["indices"])
    count = positions[3]
    index_count = indices[3]

    mins = doc["accessors"][primitive["attributes"]["POSITION"]]["min"]
    maxs = doc["accessors"][primitive["attributes"]["POSITION"]]["max"]
    min_x, min_y, min_z = mins
    max_x, max_y, max_z = maxs
    span_x = max_x - min_x
    span_y = max_y - min_y
    span_z = max_z - min_z

    # Project the wall's X/Z plane into image space and encode relief depth from Y.
    proj_x = array("f", [0.0]) * count
    proj_y = array("f", [0.0]) * count
    proj_h = array("f", [0.0]) * count
    depth = array("f", [-1.0]) * (size * size)

    for i in range(count):
        x, y, z = read_vec3(positions, i)
        proj_x[i] = (x - min_x) / span_x * (size - 1)
        proj_y[i] = (1.0 - (z - min_z) / span_z) * (size - 1)
        proj_h[i] = (y - min_y) / span_y

    for i in range(0, index_count, 3):
        ia = read_index(indices, i)
        ib = read_index(indices, i + 1)
        ic = read_index(indices, i + 2)
        ax, ay, ah = proj_x[ia], proj_y[ia], proj_h[ia]
        bx, by, bh = proj_x[ib], proj_y[ib], proj_h[ib]
        cx, cy, ch = proj_x[ic], proj_y[ic], proj_h[ic]

        min_px = max(0, int(math.floor(min(ax, bx, cx))))
        max_px = min(size - 1, int(math.ceil(max(ax, bx, cx))))
        min_py = max(0, int(math.floor(min(ay, by, cy))))
        max_py = min(size - 1, int(math.ceil(max(ay, by, cy))))
        if min_px > max_px or min_py > max_py:
            continue

        denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denom) < 1e-10:
            x = int(round((ax + bx + cx) / 3.0))
            y = int(round((ay + by + cy) / 3.0))
            if 0 <= x < size and 0 <= y < size:
                idx = y * size + x
                h = max(ah, bh, ch)
                if h > depth[idx]:
                    depth[idx] = h
            continue

        inv_denom = 1.0 / denom
        for y in range(min_py, max_py + 1):
            row = y * size
            py = y + 0.5
            for x in range(min_px, max_px + 1):
                px = x + 0.5
                wa = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) * inv_denom
                if wa < -0.001:
                    continue
                wb = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) * inv_denom
                if wb < -0.001:
                    continue
                wc = 1.0 - wa - wb
                if wc < -0.001:
                    continue
                h = wa * ah + wb * bh + wc * ch
                idx = row + x
                if h > depth[idx]:
                    depth[idx] = h

    # Fill tiny projection holes from nearest populated neighbors.
    for _ in range(8):
        changed = 0
        new_depth = array("f", depth)
        for y in range(size):
            row = y * size
            for x in range(size):
                idx = row + x
                if depth[idx] >= 0.0:
                    continue
                total = 0.0
                n = 0
                for oy in (-1, 0, 1):
                    yy = y + oy
                    if yy < 0 or yy >= size:
                        continue
                    for ox in (-1, 0, 1):
                        xx = x + ox
                        if xx < 0 or xx >= size or (ox == 0 and oy == 0):
                            continue
                        v = depth[yy * size + xx]
                        if v >= 0.0:
                            total += v
                            n += 1
                if n:
                    new_depth[idx] = total / n
                    changed += 1
        depth = new_depth
        if changed == 0:
            break

    coverage = bytearray(size * size)
    for i, v in enumerate(depth):
        coverage[i] = 255 if v >= 0.0 else 0

    # Light smoothing reduces point splat noise while preserving actual relief ranges.
    for _ in range(2):
        smoothed = array("f", depth)
        for y in range(1, size - 1):
            row = y * size
            for x in range(1, size - 1):
                idx = row + x
                smoothed[idx] = (
                    depth[idx] * 4.0
                    + depth[idx - 1]
                    + depth[idx + 1]
                    + depth[idx - size]
                    + depth[idx + size]
                ) / 8.0
        depth = smoothed

    # Use robust percentiles so accidental outliers do not crush the subtle relief.
    populated = sorted(v for v in depth if v >= 0.0)
    lo = populated[int(len(populated) * 0.002)]
    hi = populated[int(len(populated) * 0.998)]
    if hi <= lo:
        lo, hi = min_y, max_y

    height_bytes = bytearray(size * size)
    mask_bytes = bytearray(coverage)
    normal_rgb = bytearray(size * size * 3)
    shade_rgb = bytearray(size * size * 3)
    light = (-0.45, 0.55, 0.70)
    light_len = math.sqrt(sum(c * c for c in light))
    light = tuple(c / light_len for c in light)

    def norm_height(v):
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))

    normalized = array("f", (norm_height(v) for v in depth))
    for y in range(size):
        for x in range(size):
            idx = y * size + x
            h = normalized[idx]
            height_bytes[idx] = int(h * 255.0 + 0.5)

            xl = max(x - 1, 0)
            xr = min(x + 1, size - 1)
            yd = max(y - 1, 0)
            yu = min(y + 1, size - 1)
            l = normalized[y * size + xl]
            r = normalized[y * size + xr]
            d = normalized[yd * size + x]
            u = normalized[yu * size + x]
            nx = (l - r) * 7.0
            ny = (d - u) * 7.0
            nz = 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            nx *= inv
            ny *= inv
            nz *= inv
            nbase = idx * 3
            normal_rgb[nbase + 0] = int((nx * 0.5 + 0.5) * 255.0 + 0.5)
            normal_rgb[nbase + 1] = int((ny * 0.5 + 0.5) * 255.0 + 0.5)
            normal_rgb[nbase + 2] = int((nz * 0.5 + 0.5) * 255.0 + 0.5)

            diffuse = (nx * light[0] + ny * light[1] + nz * light[2]) * 0.5 + 0.5
            rim = (1.0 - max(nz, 0.0)) ** 1.7
            cavity = h * (1.0 - diffuse)
            c = 0.70 * (0.74 + diffuse * 0.34) + 0.34 * rim - 0.24 * cavity
            c = max(0.0, min(1.0, c))
            shade_rgb[nbase + 0] = int(c * 255.0 + 0.5)
            shade_rgb[nbase + 1] = int(c * 255.0 + 0.5)
            shade_rgb[nbase + 2] = int(c * 255.0 + 0.5)

    height_pgm = out_dir / "baroque_height.pgm"
    mask_pgm = out_dir / "baroque_mask.pgm"
    normal_ppm = out_dir / "baroque_normal.ppm"
    shade_ppm = out_dir / "baroque_reference_2d.ppm"
    write_pgm(height_pgm, height_bytes, size, size)
    write_pgm(mask_pgm, mask_bytes, size, size)
    write_ppm(normal_ppm, normal_rgb, size, size)
    write_ppm(shade_ppm, shade_rgb, size, size)
    ffmpeg_convert(height_pgm, out_dir / "baroque_height.png")
    ffmpeg_convert(mask_pgm, out_dir / "baroque_mask.png")
    ffmpeg_convert(normal_ppm, out_dir / "baroque_normal.png")
    ffmpeg_convert(shade_ppm, out_dir / "baroque_reference_2d.png")

    metadata = {
        "source": str(glb),
        "resolution": [size, size],
        "projection": "x/z plane",
        "height_axis": "y",
        "position_min": mins,
        "position_max": maxs,
        "height_normalization": [lo, hi],
        "vertex_count": count,
        "triangle_count": index_count // 3,
    }
    (out_dir / "baroque_bake_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
