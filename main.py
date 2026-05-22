import argparse
from pathlib import Path
from typing import cast, Dict, Tuple
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.pens.ttGlyphPen import TTGlyphPen


def draw_skeleton_shapes(
    font: TTFont, args: argparse.Namespace
) -> Dict[str, Tuple[Glyph, int]]:
    """
    Calculates metrics based on character '0' and generates TrueType glyph definitions.
    """
    glyph_set: Dict[str, Glyph] = cast(Dict[str, Glyph], font.getGlyphSet())

    glyf_table = font["glyf"]

    # Target character '0' (or fallback) to extract metrics
    zero_glyph_name = "zero" if "zero" in glyph_set else "uni0030"

    if zero_glyph_name in glyph_set:
        zero_glyph = glyf_table[zero_glyph_name]
        ymin, ymax = int(zero_glyph.yMin), int(zero_glyph.yMax)
        # Get advance width from hmtx table safely
        zero_width = int(font["hmtx"][zero_glyph_name][0])
    else:
        # Secure fallback constants standard to TrueType metrics
        ymin, ymax = 0, int(font["head"].unitsPerEm * 0.7)  # pyright: ignore[reportAttributeAccessIssue]
        zero_width = int(font["head"].unitsPerEm * 0.5)  # pyright: ignore[reportAttributeAccessIssue]

    zero_height = ymax - ymin

    # Calculate exact bounding boxes
    skel_height = int(zero_height * args.height_scale)
    skel_width = int(zero_width)
    skel_y_center = int((ymin + ymax) / 2 + args.y_offset)

    y_top = int(skel_y_center + (skel_height / 2))
    y_bottom = int(skel_y_center - (skel_height / 2))
    x_left = 0
    x_right = skel_width
    r = int(skel_height * min(max(args.corner_round, 0.0), 0.5))

    # Magic constant for cubic-to-quadratic Bezier circles
    kappa = 0.5522847498
    offset = int(r * kappa)

    generated_glyphs: Dict[str, Tuple[Glyph, int]] = {}

    # --- Variant 1: block_fill (Full block) ---
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_left, y_top))
    pen.lineTo((x_right, y_top))
    pen.lineTo((x_right, y_bottom))
    pen.lineTo((x_left, y_bottom))
    pen.closePath()
    generated_glyphs["skel_fill"] = (pen.glyph(), skel_width)

    # --- Variant 2: block_left (Left rounded cap) ---
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_right, y_top))
    pen.lineTo((x_right, y_bottom))
    pen.lineTo((x_left + r, y_bottom))
    # Approximation using quadratic Bezier points for TTF compatibility
    pen.qCurveTo(
        (x_left + r - offset, y_bottom),
        (x_left, y_bottom + r - offset),
        (x_left, y_bottom + r),
    )
    pen.lineTo((x_left, y_top - r))
    pen.qCurveTo(
        (x_left, y_top - r + offset),
        (x_left + r - offset, y_top),
        (x_left + r, y_top),
    )
    pen.closePath()
    generated_glyphs["skel_left"] = (pen.glyph(), skel_width)

    # --- Variant 3: block_right (Right rounded cap) ---
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_left, y_top))
    pen.lineTo((x_right - r, y_top))
    pen.qCurveTo(
        (x_right - r + offset, y_top),
        (x_right, y_top - r + offset),
        (x_right, y_top - r),
    )
    pen.lineTo((x_right, y_bottom + r))
    pen.qCurveTo(
        (x_right, y_bottom + r - offset),
        (x_right - r + offset, y_bottom),
        (x_right - r, y_bottom),
    )
    pen.lineTo((x_left, y_bottom))
    pen.closePath()
    generated_glyphs["skel_right"] = (pen.glyph(), skel_width)

    return generated_glyphs


def process_variable_font(args: argparse.Namespace, font_path: Path, save_path: Path):
    try:
        font = TTFont(font_path)
    except Exception as e:
        print(f"Skipping {font_path.name}: Could not parse file. Details: {e}")
        return

    # Enforce standard TrueType Variable configuration check
    if "glyf" not in font:
        print(
            f"Skipping {font_path.name}: Outlines are PostScript (CFF2). This fix targets standard TTF variable formats."
        )
        font.close()
        return

    glyf_table = font["glyf"]
    hmtx_table = font["hmtx"]

    # 1. Generate the math-exact static loading geometries
    new_glyphs = draw_skeleton_shapes(font, args)

    # 2. Inject vector elements seamlessly into glyf and metrics tables
    glyf_table["uni2588"] = new_glyphs["skel_fill"][0]  # Full Block █
    glyf_table["uni258C"] = new_glyphs["skel_right"][
        0
    ]  # Left Half Block ▌ (Used as right-cap)
    glyf_table["uni2590"] = new_glyphs["skel_left"][
        0
    ]  # Right Half Block ▐ (Used as left-cap)

    hmtx_table["uni2588"] = (new_glyphs["skel_fill"][1], 0)
    hmtx_table["uni258C"] = (new_glyphs["skel_right"][1], 0)
    hmtx_table["uni2590"] = (new_glyphs["skel_left"][1], 0)

    # 3. Re-link character mapping tables safely
    cmap = font.getBestCmap()
    if cmap is None:
        print(f"Skipping {font_path.name}: Font cmap not available.")
        font.close()
        return
    cmap[0x2588] = "uni2588"
    cmap[0x258C] = "uni258C"
    cmap[0x2590] = "uni2590"

    # 4. Save out file
    if save_path.suffix.lower() == ".woff2":
        font.flavor = "woff2"
    font.save(save_path)
    font.close()
    print(f"Success! Output Variable Font created at:\n - {save_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Inject adaptive skeleton loading bars into an existing font file."
    )
    parser.add_argument("input_font", help="Path to input TTF/OTF font file")
    parser.add_argument(
        "--height-scale",
        type=float,
        default=0.6,
        help="Visual height of skeleton bar relative to the character '0' (0.0 to 1.0)",
    )
    parser.add_argument(
        "--y-offset",
        type=float,
        default=0.0,
        help="Shift skeleton bar up or down relative to baseline",
    )
    parser.add_argument(
        "--corner-round",
        type=float,
        default=0.5,
        help="Corner rounding radius as percentage of visual bar height (0.0 to 0.5)",
    )
    args = parser.parse_args()

    input_font_path = Path(args.input_font)
    if not input_font_path.exists():
        print(f"Error: Font file '{args.input_font}' not found.")
        return

    if input_font_path.is_dir():
        out_dir = Path(f"{input_font_path}_skeleton")
        out_dir.mkdir(exist_ok=True)
        for font_path in input_font_path.iterdir():
            if font_path.is_file() and font_path.suffix.lower() in [".ttf", ".woff"]:
                save_path = out_dir / font_path.name
                process_variable_font(args, font_path, save_path)
    else:
        if input_font_path.suffix.lower() in [".ttf", ".woff"]:
            save_path = (
                input_font_path.parent
                / f"{input_font_path.stem}_skeleton{input_font_path.suffix}"
            )
            process_variable_font(args, input_font_path, save_path)


if __name__ == "__main__":
    main()
