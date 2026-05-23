import argparse
from pathlib import Path
from typing import cast, Dict, List, Tuple
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables.TupleVariation import TupleVariation


def draw_skeleton_shapes(
    font: TTFont, args: argparse.Namespace
) -> Tuple[Dict[str, Glyph], Dict[str, List[TupleVariation]], str]:
    """
    Calculates metrics based on character zero '0' for height and em dash '—'
    for width, and generates TrueType glyph definitions.
    """
    glyf_table = font["glyf"]
    glyph_set: Dict[str, Glyph] = cast(Dict[str, Glyph], font.getGlyphSet())

    # Calculate bounding box width from emdash.
    emdash_name = "emdash" if "emdash" in glyph_set else "uni2014"
    if emdash_name not in glyph_set:
        raise ValueError(
            "Target font does not contain a suitable base horizontal em dash glyph."
        )

    em_glyph = glyf_table[emdash_name]
    x_left = float(em_glyph.xMin)
    x_right = float(em_glyph.xMax)

    # Calculate bounding box height from '0'.
    zero_name = "zero" if "zero" in glyph_set else "uni0030"
    if zero_name in glyph_set:
        zero_glyph = glyf_table[zero_name]
        ymin, ymax = float(zero_glyph.yMin), float(zero_glyph.yMax)
    else:
        ymin, ymax = 0.0, float(font["head"].unitsPerEm * 0.7)  # pyright: ignore[reportAttributeAccessIssue]

    zero_height = ymax - ymin
    skel_height = float(zero_height * args.height_scale)
    skel_y_center = float((ymin + ymax) / 2 + args.y_offset)

    y_top = float(skel_y_center + (skel_height / 2))
    y_bottom = y_top - skel_height

    corner_round = float(min(max(args.corner_round, 0.0), 0.5))
    radius = skel_height * corner_round

    if corner_round == 0.5:
        generated_glyphs = draw_semicircle_skeleton_shape_glyphs(
            glyph_set,
            y_top=y_top,
            y_bottom=y_bottom,
            x_left=x_left,
            x_right=x_right,
            radius=radius,
        )
    else:
        generated_glyphs = draw_quadratic_skeleton_shape_glyphs(
            glyph_set,
            y_top=y_top,
            y_bottom=y_bottom,
            x_left=x_left,
            x_right=x_right,
            radius=radius,
        )

    # Extract and duplicate variation mappings (gvar) directly from emdash.
    generated_variations: Dict[str, List[TupleVariation]] = {}
    if "gvar" in font and emdash_name in font["gvar"].variations:
        emdash_variations = cast(
            List[TupleVariation], font["gvar"].variations[emdash_name]
        )

        for variant_key in ("skel_fill", "skel_left", "skel_right"):
            target_glyph = generated_glyphs[variant_key]

            new_vars: List[TupleVariation] = []
            point_count = len(target_glyph.coordinates)

            for var in emdash_variations:
                if not var.coordinates:
                    continue
                # Capture structural delta boundaries from emdash master state.
                left_coord = min(
                    var.coordinates,
                    key=lambda coord: coord[0] if type(coord) is tuple else 0,
                )
                right_coord = max(
                    var.coordinates,
                    key=lambda coord: coord[0] if type(coord) is tuple else 0,
                )

                delta_left = left_coord[0] if type(left_coord) is tuple else 0
                delta_right = right_coord[0] if type(right_coord) is tuple else 0

                # CoreText compliant clean structure map.
                coords = [(0, 0) for _ in range(point_count)]

                for idx, (x, y) in enumerate(
                    cast(List[Tuple[int, int]], target_glyph.coordinates)
                ):
                    # Move control points within a radius width from the
                    # left/right boundary to properly stretch the glyph and
                    # include the rounded corners.
                    if abs(x - x_left) <= radius + 1:
                        coords[idx] = (delta_left, 0)
                    elif abs(x - x_right) <= radius + 1:
                        coords[idx] = (delta_right, 0)

                # Append explicit phantom points for CoreText.
                # [Left Side Bearing, Right Advance Width, Top Side Bearing, Bottom Advance Height]
                coords.extend([(delta_left, 0), (delta_right, 0), (0, 0), (0, 0)])
                # coords.extend([(0, 0), (0, 0), (0, 0), (0, 0)])
                new_vars.append(TupleVariation(var.axes, coords))

            generated_variations[variant_key] = new_vars

    return generated_glyphs, generated_variations, emdash_name


def draw_semicircle_skeleton_shape_glyphs(
    glyph_set: Dict[str, Glyph],
    y_top: float,
    y_bottom: float,
    x_left: float,
    x_right: float,
    radius: float,
):
    generated_glyphs: Dict[str, Glyph] = {}

    # Magic constant for 45-degree TrueType quadratic arcs: math.sqrt(2) - 1
    # This maps the exact offset needed for the mid-point anchor positions
    q_arc = 0.414213562

    # Distance from the edge of the circle bounding box to the 45-degree anchor point
    # coordinate offset: r * (1 - cos(45)) = r * (1 - 0.7071) ≈ 0.2929 * r
    # control offset: r * sin(45) * (sqrt(2)-1) is factored cleanly below
    chord_offset = float(radius * 0.2928932188)
    control_offset = float(radius * q_arc)

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
    # Curves on the left, flat on the right.
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_right, y_top))
    pen.lineTo((x_right, y_bottom))
    pen.lineTo((x_left + radius, y_bottom))

    # Bottom-Left Quadrant (split into two 45-degree steps)
    pen.qCurveTo(
        (x_left + radius - control_offset, y_bottom),  # Handle 1
        (
            x_left + chord_offset,
            y_bottom + chord_offset,
        ),  # 45-degree mid on-curve point
    )
    pen.qCurveTo(
        (x_left, y_bottom + radius - control_offset),  # Handle 2
        (x_left, y_bottom + radius),  # End of quadrant
    )

    # Straight vertical line on left side (collapses cleanly to 0 length when radius = 0.5 * height)
    pen.lineTo((x_left, y_top - radius))

    # Top-Left Quadrant (split into two 45-degree steps)
    pen.qCurveTo(
        (x_left, y_top - radius + control_offset),  # Handle 1
        (x_left + chord_offset, y_top - chord_offset),  # 45-degree mid on-curve point
    )
    pen.qCurveTo(
        (x_left + radius - control_offset, y_top),  # Handle 2
        (x_left + radius, y_top),  # End of quadrant
    )

    pen.closePath()
    generated_glyphs["skel_left"] = pen.glyph()

    # --- Variant 3: block_right (Right rounded cap) ---
    # Curves on the right, flat on the left.
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_left, y_top))
    pen.lineTo((x_right - radius, y_top))

    # Top-Right Quadrant (split into two 45-degree steps)
    pen.qCurveTo(
        (x_right - radius + control_offset, y_top),  # Handle 1
        (x_right - chord_offset, y_top - chord_offset),  # 45-degree mid on-curve point
    )
    pen.qCurveTo(
        (x_right, y_top - radius + control_offset),  # Handle 2
        (x_right, y_top - radius),  # End of quadrant
    )

    # Straight vertical line on right side
    pen.lineTo((x_right, y_bottom + radius))

    # Bottom-Right Quadrant (split into two 45-degree steps)
    pen.qCurveTo(
        (x_right, y_bottom + radius - control_offset),  # Handle 1
        (
            x_right - chord_offset,
            y_bottom + chord_offset,
        ),  # 45-degree mid on-curve point
    )
    pen.qCurveTo(
        (x_right - radius + control_offset, y_bottom),  # Handle 2
        (x_right - radius, y_bottom),  # End of quadrant
    )

    pen.lineTo((x_left, y_bottom))
    pen.closePath()
    generated_glyphs["skel_right"] = pen.glyph()

    return generated_glyphs


def draw_quadratic_skeleton_shape_glyphs(
    glyph_set: Dict[str, Glyph],
    y_top: float,
    y_bottom: float,
    x_left: float,
    x_right: float,
    radius: float,
):
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
    # Has a flat right edge, curves are on the left side
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_right, y_top))
    pen.lineTo((x_right, y_bottom))
    pen.lineTo((x_left + radius, y_bottom))

    # Bottom-left corner arc: Control point is exactly at the virtual sharp corner (x_left, y_bottom)
    pen.qCurveTo((x_left, y_bottom), (x_left, y_bottom + radius))

    # Straight vertical line on the left side (only exists if radius is less than 0.5 * height)
    pen.lineTo((x_left, y_top - radius))

    # Top-left corner arc: Control point is exactly at (x_left, y_top)
    pen.qCurveTo((x_left, y_top), (x_left + radius, y_top))
    pen.closePath()
    generated_glyphs["skel_left"] = pen.glyph()

    # --- Variant 3: block_right (Right rounded cap) ---
    # Has a flat left edge, curves are on the right side
    pen = TTGlyphPen(glyph_set)
    pen.moveTo((x_left, y_top))
    pen.lineTo((x_right - radius, y_top))

    # Top-right corner arc: Control point sits at (x_right, y_top)
    pen.qCurveTo((x_right, y_top), (x_right, y_top - radius))

    # Straight vertical line on the right side
    pen.lineTo((x_right, y_bottom + radius))

    # Bottom-right corner arc: Control point sits at (x_right, y_bottom)
    pen.qCurveTo((x_right, y_bottom), (x_right - radius, y_bottom))
    pen.lineTo((x_left, y_bottom))
    pen.closePath()
    generated_glyphs["skel_right"] = pen.glyph()

    return generated_glyphs


def fix_hvar(font: TTFont, emdash_name: str):
    """
    Finds the HVAR width variation mapping index for the base emdash glyph and
    copies it to the newly injected skeleton loading bar glyphs.
    """
    if "HVAR" not in font:
        return

    hvar_table = font["HVAR"].table
    glyph_order = font.getGlyphOrder()
    target_glyphs = ("uni2588", "uni258C", "uni2590")

    if hasattr(hvar_table, "VarIdxMap"):
        print("Fixing VarIdxMap")
        var_idx_map = hvar_table.VarIdxMap
        if emdash_name in var_idx_map.mapping:
            emdash_idx = var_idx_map.mapping[emdash_name]
            for glyph in target_glyphs:
                if glyph in glyph_order:
                    var_idx_map.mapping[glyph] = emdash_idx

    if hasattr(hvar_table, "AdvWidthMap") and hvar_table.AdvWidthMap is not None:
        width_map = hvar_table.AdvWidthMap.mapping
        if emdash_name in width_map:
            emdash_idx = width_map[emdash_name]
            for glyph in target_glyphs:
                if glyph in glyph_order:
                    width_map[glyph] = emdash_idx

    # Side-bearings maps are optional components in HVAR.
    # If present, map them to the emdash values too to ensure layout engines
    # don't get confused by shifting bounding boxes.
    if hasattr(hvar_table, "LsbMap") and hvar_table.LsbMap is not None:
        lsb_map = hvar_table.LsbMap.mapping
        if emdash_name in lsb_map:
            emdash_lsb_idx = lsb_map[emdash_name]
            for glyph in target_glyphs:
                if glyph in glyph_order:
                    lsb_map[glyph] = emdash_lsb_idx

    if hasattr(hvar_table, "RsbMap") and hvar_table.RsbMap is not None:
        rsb_map = hvar_table.RsbMap.mapping
        if emdash_name in rsb_map:
            emdash_rsb_idx = rsb_map[emdash_name]
            for glyph in target_glyphs:
                if glyph in glyph_order:
                    rsb_map[glyph] = emdash_rsb_idx


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
    new_glyphs, new_variations, emdash_name = draw_skeleton_shapes(font, args)

    # Assign base structural paths.
    glyf_table["uni2588"] = new_glyphs["skel_fill"]
    glyf_table["uni258C"] = new_glyphs["skel_right"]
    glyf_table["uni2590"] = new_glyphs["skel_left"]

    # Inherit absolute advance metrics verbatim from emdash.
    hmtx_table["uni2588"] = hmtx_table[emdash_name]
    hmtx_table["uni258C"] = hmtx_table[emdash_name]
    hmtx_table["uni2590"] = hmtx_table[emdash_name]

    # Map the variation matrices.
    if "gvar" in font and new_variations:
        gvar_table = font["gvar"]

        # Adapt tracking deltas from emdash.
        gvar_table.variations["uni2588"] = new_variations["skel_fill"]
        gvar_table.variations["uni258C"] = new_variations["skel_right"]
        gvar_table.variations["uni2590"] = new_variations["skel_left"]

        # Keep maxp limits safely aligned for iOS CoreText layout limits
        if "maxp" in font and hasattr(font["maxp"], "maxPoints"):
            max_pts = max(len(g.coordinates) for g in new_glyphs.values())
            font["maxp"].maxPoints = max(cast(int, font["maxp"].maxPoints), max_pts + 4)

        # Update metric overrides
        fix_hvar(font, emdash_name)

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
    print(f"Success! Output font created at:\n - {save_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Inject adaptive skeleton loading bars into an existing font file."
    )
    parser.add_argument(
        "input_font",
        help="Path to input TTF/WOFF font file or directory containing font files",
    )
    parser.add_argument(
        "--output", type=str, help="Output file or directory for updated fonts"
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
        default=0.45,
        help="Corner rounding radius as percentage of visual bar height (0.0 to 0.5)",
    )
    args = parser.parse_args()

    input_font_path = Path(args.input_font)
    if not input_font_path.exists():
        print(f"Error: Font file '{args.input_font}' not found.")
        return

    if input_font_path.is_dir():
        out_dir = (
            Path(args.output)
            if args.output is not None
            else Path(f"{input_font_path}_skeleton")
        )
        out_dir.mkdir(exist_ok=True)
        for font_path in input_font_path.iterdir():
            if font_path.is_file() and font_path.suffix.lower() in (
                ".ttf",
                ".otf",
                ".woff2",
            ):
                save_path = out_dir / font_path.name
                process_font(args, font_path, save_path)
            else:
                print(f"Unsupported font file: {font_path}")
    else:
        if input_font_path.suffix.lower() in [".ttf", ".otf", ".woff2"]:
            save_path = (
                Path(args.output)
                if args.output is not None
                else (
                    input_font_path.parent
                    / f"{input_font_path.stem}_skeleton{input_font_path.suffix}"
                )
            )
            process_font(args, input_font_path, save_path)
        else:
            print(f"Unsupported font file: {input_font_path}")


if __name__ == "__main__":
    main()
