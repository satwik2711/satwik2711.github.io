#!/usr/bin/env python3
"""Generate pixel-art triangle landscapes with no third-party dependencies.

The arrangement matches the floating, asymmetrical composition used across this
site: a large central triangle, four smaller fragments, and a reflected piece
below. Every rendered pixel is an integer-sized block, so the PNG stays crisp
when it is scaled in a browser.

Examples:
    python3 scripts/generate_triangle_art.py
    python3 scripts/generate_triangle_art.py --scheme ocean --background midnight
    python3 scripts/generate_triangle_art.py --scheme sunset --background cream --seed 42
    python3 scripts/generate_triangle_art.py --list-options
"""

from __future__ import annotations

import argparse
import random
import struct
import zlib
from pathlib import Path


LOGICAL_WIDTH = 400
LOGICAL_HEIGHT = 225

PALETTES = {
    "forest": {
        "sky": (205, 226, 179), "sky_low": (129, 183, 122), "sun": (244, 239, 205),
        "far": (128, 179, 113), "mid": (73, 138, 94), "near": (41, 103, 73),
        "ground": (25, 80, 58), "tree_a": (17, 61, 47), "tree_b": (12, 47, 38),
        "accent": (231, 244, 199), "outline": (5, 25, 20),
    },
    "ocean": {
        "sky": (139, 213, 237), "sky_low": (38, 159, 205), "sun": (229, 248, 241),
        "far": (63, 165, 200), "mid": (25, 125, 171), "near": (18, 89, 139),
        "ground": (12, 62, 108), "tree_a": (8, 49, 87), "tree_b": (5, 37, 68),
        "accent": (213, 248, 249), "outline": (3, 18, 36),
    },
    "sunset": {
        "sky": (255, 205, 150), "sky_low": (209, 111, 111), "sun": (255, 242, 193),
        "far": (202, 120, 114), "mid": (153, 75, 99), "near": (101, 55, 84),
        "ground": (67, 40, 67), "tree_a": (49, 31, 55), "tree_b": (35, 23, 43),
        "accent": (255, 224, 182), "outline": (25, 14, 33),
    },
    "mono": {
        "sky": (221, 225, 206), "sky_low": (146, 162, 145), "sun": (245, 245, 228),
        "far": (145, 161, 143), "mid": (94, 116, 103), "near": (59, 83, 76),
        "ground": (38, 59, 55), "tree_a": (29, 47, 44), "tree_b": (19, 34, 32),
        "accent": (242, 244, 221), "outline": (10, 20, 19),
    },
}

BACKGROUNDS = {
    "transparent": None,
    "black": (0, 0, 0),
    "cream": (248, 244, 234),
    "midnight": (6, 23, 19),
}


class Bitmap:
    def __init__(self, width: int, height: int, fill: tuple[int, int, int] | None = None):
        self.width = width
        self.height = height
        base = (0, 0, 0, 0) if fill is None else (*fill, 255)
        self.data = bytearray(base * (width * height))

    def index(self, x: int, y: int) -> int:
        return (y * self.width + x) * 4

    def set(self, x: int, y: int, colour: tuple[int, int, int], alpha: int = 255) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            index = self.index(x, y)
            self.data[index:index + 4] = bytes((*colour, alpha))

    def get(self, x: int, y: int) -> tuple[int, int, int, int]:
        index = self.index(x, y)
        return tuple(self.data[index:index + 4])  # type: ignore[return-value]

    def fill_rect(self, x: int, y: int, width: int, height: int, colour: tuple[int, int, int]) -> None:
        for row in range(max(0, y), min(self.height, y + height)):
            for column in range(max(0, x), min(self.width, x + width)):
                self.set(column, row, colour)


def inside_triangle(x: float, y: float, points: list[tuple[int, int]]) -> bool:
    """Return whether a pixel centre is inside an arbitrary triangle."""
    (ax, ay), (bx, by), (cx, cy) = points
    d1 = (x - cx) * (by - cy) - (bx - cx) * (y - cy)
    d2 = (x - ax) * (cy - ay) - (cx - ax) * (y - ay)
    d3 = (x - bx) * (ay - by) - (ax - bx) * (y - by)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def fill_polygon(canvas: Bitmap, points: list[tuple[int, int]], colour: tuple[int, int, int]) -> None:
    minimum_x = max(0, min(point[0] for point in points))
    maximum_x = min(canvas.width - 1, max(point[0] for point in points))
    minimum_y = max(0, min(point[1] for point in points))
    maximum_y = min(canvas.height - 1, max(point[1] for point in points))
    for y in range(minimum_y, maximum_y + 1):
        intersections = []
        for index, (x1, y1) in enumerate(points):
            x2, y2 = points[(index + 1) % len(points)]
            if (y1 <= y < y2) or (y2 <= y < y1):
                intersections.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        intersections.sort()
        for start, end in zip(intersections[::2], intersections[1::2]):
            for x in range(max(minimum_x, int(start)), min(maximum_x, int(end)) + 1):
                canvas.set(x, y, colour)


def fill_circle(canvas: Bitmap, centre_x: int, centre_y: int, radius: int, colour: tuple[int, int, int]) -> None:
    for y in range(centre_y - radius, centre_y + radius + 1):
        for x in range(centre_x - radius, centre_x + radius + 1):
            if (x - centre_x) ** 2 + (y - centre_y) ** 2 <= radius ** 2:
                canvas.set(x, y, colour)


def draw_tree(canvas: Bitmap, x: int, base_y: int, height: int, colour: tuple[int, int, int]) -> None:
    canvas.fill_rect(x, base_y - height // 3, max(1, height // 12), height // 3, colour)
    for depth, width_factor in ((0, .18), (1, .29), (2, .39)):
        top = base_y - height + int(height * depth * .22)
        bottom = top + int(height * .48)
        half_width = max(2, int(height * width_factor))
        fill_polygon(canvas, [(x, top), (x - half_width, bottom), (x + half_width, bottom)], colour)


def make_landscape(seed: int, palette: dict[str, tuple[int, int, int]]) -> Bitmap:
    rng = random.Random(seed)
    scene = Bitmap(LOGICAL_WIDTH, LOGICAL_HEIGHT)
    sky_bands = [palette["sky"], palette["sky"], palette["sky"], palette["sky_low"], palette["sky_low"]]
    band_height = LOGICAL_HEIGHT // len(sky_bands)
    for index, colour in enumerate(sky_bands):
        scene.fill_rect(0, index * band_height, LOGICAL_WIDTH, band_height + 1, colour)

    fill_circle(scene, 214, 72, 18, palette["sun"])
    for x, y in ((229, 58), (240, 55), (251, 61), (263, 50), (278, 56)):
        scene.set(x, y, palette["accent"])
        scene.set(x + 2, y, palette["accent"])

    fill_polygon(scene, [(0, 125), (40, 82), (78, 110), (119, 65), (158, 116), (203, 89), (242, 121), (284, 70), (327, 108), (365, 61), (400, 101), (400, 225), (0, 225)], palette["far"])
    fill_polygon(scene, [(0, 151), (49, 116), (88, 142), (138, 94), (182, 149), (226, 112), (271, 153), (319, 107), (360, 143), (400, 106), (400, 225), (0, 225)], palette["mid"])
    fill_polygon(scene, [(0, 175), (46, 143), (98, 172), (150, 130), (199, 179), (246, 137), (294, 175), (340, 132), (400, 170), (400, 225), (0, 225)], palette["near"])
    fill_polygon(scene, [(0, 190), (65, 166), (132, 193), (191, 159), (257, 196), (322, 165), (400, 190), (400, 225), (0, 225)], palette["ground"])

    for _ in range(52):
        x = rng.randrange(-5, LOGICAL_WIDTH + 5)
        base_y = rng.randrange(184, 225)
        height = rng.randrange(11, 31)
        draw_tree(scene, x, base_y, height, palette["tree_a"] if rng.random() > .45 else palette["tree_b"])

    for y in range(4, LOGICAL_HEIGHT, 5):
        for x in range((y * 7) % 13, LOGICAL_WIDTH, 17):
            red, green, blue, alpha = scene.get(x, y)
            if alpha:
                scene.data[scene.index(x, y):scene.index(x, y) + 4] = bytes((max(0, red - 8), max(0, green - 8), max(0, blue - 8), alpha))
    return scene


def triangle_layout() -> list[list[tuple[int, int]]]:
    """The fixed six-piece alignment used by the original artwork."""
    return [
        [(210, 58), (145, 176), (278, 176)],
        [(142, 72), (204, 72), (173, 129)],
        [(111, 80), (84, 128), (140, 128)],
        [(270, 80), (332, 80), (301, 135)],
        [(325, 96), (295, 144), (352, 144)],
        [(210, 178), (267, 178), (238, 222)],
    ]


def draw_line(canvas: Bitmap, start: tuple[int, int], end: tuple[int, int], colour: tuple[int, int, int]) -> None:
    x1, y1 = start
    x2, y2 = end
    dx, dy = abs(x2 - x1), -abs(y2 - y1)
    step_x, step_y = (1 if x1 < x2 else -1), (1 if y1 < y2 else -1)
    error = dx + dy
    while True:
        canvas.set(x1, y1, colour)
        if (x1, y1) == (x2, y2):
            return
        double_error = 2 * error
        if double_error >= dy:
            error += dy
            x1 += step_x
        if double_error <= dx:
            error += dx
            y1 += step_y


def compose(seed: int, scheme: str, background: str) -> Bitmap:
    palette = PALETTES[scheme]
    output = Bitmap(LOGICAL_WIDTH, LOGICAL_HEIGHT, BACKGROUNDS[background])
    scene = make_landscape(seed, palette)
    for points in triangle_layout():
        minimum_x = max(0, min(x for x, _ in points))
        maximum_x = min(LOGICAL_WIDTH - 1, max(x for x, _ in points))
        minimum_y = max(0, min(y for _, y in points))
        maximum_y = min(LOGICAL_HEIGHT - 1, max(y for _, y in points))
        for y in range(minimum_y, maximum_y + 1):
            for x in range(minimum_x, maximum_x + 1):
                if inside_triangle(x + .5, y + .5, points):
                    source = scene.index(x, y)
                    destination = output.index(x, y)
                    output.data[destination:destination + 4] = scene.data[source:source + 4]
        for start, end in zip(points, points[1:] + points[:1]):
            draw_line(output, start, end, palette["outline"])
    return output


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def write_png(bitmap: Bitmap, pixel_scale: int, output: Path) -> None:
    width, height = bitmap.width * pixel_scale, bitmap.height * pixel_scale
    rows = bytearray()
    for source_y in range(bitmap.height):
        expanded = bytearray()
        for source_x in range(bitmap.width):
            pixel = bitmap.data[bitmap.index(source_x, source_y):bitmap.index(source_x, source_y) + 4]
            expanded.extend(pixel * pixel_scale)
        rows.extend((b"\x00" + bytes(expanded)) * pixel_scale)
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + png_chunk(b"IEND", b""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a pixel-art landscape revealed through floating triangles.")
    parser.add_argument("--scheme", choices=PALETTES, default="forest", help="Colour scheme (default: forest).")
    parser.add_argument("--background", choices=BACKGROUNDS, default="transparent", help="Canvas background (default: transparent).")
    parser.add_argument("--seed", type=int, default=2711, help="Seed for the forest arrangement (default: 2711).")
    parser.add_argument("--pixel-scale", type=int, default=6, choices=range(1, 17), metavar="1-16", help="Size of one art pixel in output pixels (default: 6).")
    parser.add_argument("--output", type=Path, default=Path("artifacts/images/triangle-pixel.png"), help="Destination PNG path.")
    parser.add_argument("--list-options", action="store_true", help="Print available schemes and backgrounds, then exit.")
    args = parser.parse_args()
    if args.list_options:
        print("Schemes: " + ", ".join(PALETTES))
        print("Backgrounds: " + ", ".join(BACKGROUNDS))
        return
    write_png(compose(args.seed, args.scheme, args.background), args.pixel_scale, args.output)
    print(f"Wrote {args.output} — {args.scheme} scheme on {args.background} background, seed {args.seed}.")


if __name__ == "__main__":
    main()
