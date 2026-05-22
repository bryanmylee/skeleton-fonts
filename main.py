import argparse
from pathlib import Path
from typing import cast, Dict, List, Tuple
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.pens.ttGlyphPen import TTGlyphPen


def draw_skeleton_shapes(
    font: TTFont, args: argparse.Namespace
) -> Tuple[Dict[str, Glyph], str, int]:
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
    radius = int(skel_height * min(max(args.corner_round, 0.0), 0.5))

    # Magic constant for cubic-to-quadratic Bezier circles
    kappa = 0.5522847498
    offset = int(radius * kappa)

    generated_glyphs: Dict[str, Glyph] = {}

    # --- Variant 1: block_fill (Full block) ---
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_left, y_top))
    pen.lineTo((x_right, y_top))
    pen.lineTo((x_right, y_bottom))
    pen.lineTo((x_left, y_bottom))
    pen.closePath()
    generated_glyphs["skel_fill"] = pen.glyph()

    # --- Variant 2: block_left (Left rounded cap) ---
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_right, y_top))
    pen.lineTo((x_right, y_bottom))
    pen.lineTo((x_left + radius, y_bottom))
    # Approximation using quadratic Bezier points for TTF compatibility
    pen.qCurveTo(
        (x_left + radius - offset, y_bottom),
        (x_left, y_bottom + radius - offset),
        (x_left, y_bottom + radius),
    )
    pen.lineTo((x_left, y_top - radius))
    pen.qCurveTo(
        (x_left, y_top - radius + offset),
        (x_left + radius - offset, y_top),
        (x_left + radius, y_top),
    )
    pen.closePath()
    generated_glyphs["skel_left"] = pen.glyph()

    # --- Variant 3: block_right (Right rounded cap) ---
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_left, y_top))
    pen.lineTo((x_right - radius, y_top))
    pen.qCurveTo(
        (x_right - radius + offset, y_top),
        (x_right, y_top - radius + offset),
        (x_right, y_top - radius),
    )
    pen.lineTo((x_right, y_bottom + radius))
    pen.qCurveTo(
        (x_right, y_bottom + radius - offset),
        (x_right - radius + offset, y_bottom),
        (x_right - radius, y_bottom),
    )
    pen.lineTo((x_left, y_bottom))
    pen.closePath()
    generated_glyphs["skel_right"] = pen.glyph()

    return generated_glyphs, zero_glyph_name, radius


def apply_variable_deltas(
    font: TTFont,
    target_glyph_name: str,
    zero_glyph_name: str,
    point_count: int,
    right_side_indices: List[int],
):
    """
    Safely calculates and binds point-matched variations for new geometries by
    extracting explicit axis variations directly from the gvar table framework.
    """
    if "gvar" not in font or zero_glyph_name not in font["gvar"].variations:
        return
    gvar_table = font["gvar"]
    zero_variations = cast(List[TupleVariation], gvar_table.variations[zero_glyph_name])
    new_variations: List[TupleVariation] = []

    for var in zero_variations:
        delta_width = 0

        # Method 1: Look for an explicit advance width delta in the coordinates
        # tracking.
        if var.coordinates:
            # Check the raw coordinates array length provided by the font
            # compiler Some compilers include phantom points explicitly in the
            # array
            phantom_idx = len(var.coordinates) - 4
            if (
                0 <= phantom_idx < len(var.coordinates)
                and var.coordinates[phantom_idx] is not None
            ):
                coord = var.coordinates[phantom_idx]
                if isinstance(coord, tuple) and coord[0] != 0:
                    delta_width = coord[0]

        # Method 2: If the phantom point delta was optimized away (0, 0), find
        # the point on the far right edge of the 'zero' glyph outline and copy
        # its X shift.
        if delta_width == 0 and var.coordinates:
            zero_base_glyph = font["glyf"][zero_glyph_name]

            # Find the index of the point closest to the right-most bounding
            # edge of zero.
            max_x = -99999
            rightmost_point_idx = 0

            # Loop through default base points to find the right-edge anchor
            # index.
            for i, pt in enumerate(zero_base_glyph.coordinates):
                if pt[0] > max_x:
                    max_x = pt[0]
                    rightmost_point_idx = i

            # Extract how much that specific right edge point shifted under
            # this master state.
            if (
                rightmost_point_idx < len(var.coordinates)
                and var.coordinates[rightmost_point_idx] is not None
            ):
                edge_coord = var.coordinates[rightmost_point_idx]
                if isinstance(edge_coord, tuple):
                    delta_width = edge_coord[0]

        if delta_width == 0:
            continue

        # Create a completely clean structural coordinate delta map custom
        # built for our point setup. Every index initialized to (0, 0) means it
        # stays completely stationary on that axis.
        coords = [(0, 0)] * point_count

        # Apply the exact master width expansion delta exclusively to the
        # right-side vector points
        for idx in right_side_indices:
            if idx < point_count:
                coords[idx] = (delta_width, 0)

        # Append phantom points to our delta array so formatting doesn't throw
        # compilation exceptions.
        coords.extend([(0, 0), (delta_width, 0), (0, 0), (0, 0)])

        new_var = TupleVariation(var.axes, coords)
        new_variations.append(new_var)

    if new_variations:
        gvar_table.variations[target_glyph_name] = new_variations


def process_font(args: argparse.Namespace, font_path: Path, save_path: Path):
    try:
        font = TTFont(font_path)
    except Exception as e:
        print(f"Skipping {font_path.name}: Could not parse file. Details: {e}")
        return

    # Enforce standard TrueType Variable configuration check.
    if "glyf" not in font:
        print(
            f"Skipping {font_path.name}: Outlines are PostScript (CFF2). This fix targets standard TTF variable formats."
        )
        font.close()
        return

    glyf_table = font["glyf"]
    hmtx_table = font["hmtx"]

    # Generate the math-exact static loading geometries.
    new_glyphs, zero_name, radius = draw_skeleton_shapes(font, args)

    # Assign base outlines.
    # Full Block █
    glyf_table["uni2588"] = new_glyphs["skel_fill"]
    # Left Half Block ▌ (Used as right-cap)
    glyf_table["uni258C"] = new_glyphs["skel_right"]
    # Right Half Block ▐ (Used as left-cap)
    glyf_table["uni2590"] = new_glyphs["skel_left"]

    # Setup automatic uniform baseline advanced tracking metrics.
    skel_width = cast(int, hmtx_table[zero_name][0])
    hmtx_table["uni2588"] = (skel_width, 0)
    hmtx_table["uni258C"] = (skel_width, 0)
    hmtx_table["uni2590"] = (skel_width, 0)

    # Apply precise, structural deltas to the right-side vertices of our new shapes.
    # We pass the exact indices of points that sit on the right edge of our geometry.
    if "gvar" in font:

        def get_right_side_indices(glyph_obj, right_x: int) -> List[int]:
            indices = []
            if hasattr(glyph_obj, "coordinates"):
                for idx, (x, y) in enumerate(glyph_obj.coordinates):
                    # Use the radius + 1-unit tolerance threshold to move the
                    # entire rounded cap instead of stretching the cap.
                    if abs(x - right_x) <= radius + 1:
                        indices.append(idx)
            return indices

        # Stretch uni2588 (Full Block) to fill the full glyph.
        apply_variable_deltas(
            font,
            "uni2588",
            zero_name,
            point_count=len(glyf_table["uni2588"].coordinates),
            right_side_indices=get_right_side_indices(
                glyf_table["uni2588"], skel_width
            ),
        )

        # Stretch uni258C (Right Cap) to fill the full glyph.
        apply_variable_deltas(
            font,
            "uni258C",
            zero_name,
            point_count=len(glyf_table["uni258C"].coordinates),
            right_side_indices=get_right_side_indices(
                glyf_table["uni258C"], skel_width
            ),
        )

        # Stretch uni2588 (Left Cap) to fill the full glyph.
        apply_variable_deltas(
            font,
            "uni2590",
            zero_name,
            point_count=len(glyf_table["uni2590"].coordinates),
            right_side_indices=get_right_side_indices(
                glyf_table["uni2588"], skel_width
            ),
        )

    # Re-link character mapping tables.
    cmap = font.getBestCmap()
    if cmap is None:
        print(f"Skipping {font_path.name}: Font cmap not available.")
        font.close()
        return
    cmap[0x2588] = "uni2588"
    cmap[0x258C] = "uni258C"
    cmap[0x2590] = "uni2590"

    # Save out file.
    if save_path.suffix.lower() == ".woff2":
        font.flavor = "woff2"
    font.save(save_path)
    font.close()
    print(f"Success! Output Variable Font created at:\n - {save_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Inject adaptive skeleton loading bars into an existing font file."
    )
    parser.add_argument(
        "input_font",
        help="Path to input TTF/WOFF font file or directory containing font files",
    )
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
                process_font(args, font_path, save_path)
    else:
        if input_font_path.suffix.lower() in [".ttf", ".woff"]:
            save_path = (
                input_font_path.parent
                / f"{input_font_path.stem}_skeleton{input_font_path.suffix}"
            )
            process_font(args, input_font_path, save_path)


if __name__ == "__main__":
    main()
