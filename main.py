import argparse
from pathlib import Path
from typing import cast, Dict, List, Tuple
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.pens.ttGlyphPen import TTGlyphPen


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
                # For all variations, the layout container metrics scale
                # exactly like the em dash.
                coords.extend([(delta_left, 0), (delta_right, 0), (0, 0), (0, 0)])
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

        # Force structural cast to integer to pass iOS's CoreText validation
        # parameters
        int_delta_width = int(round(delta_width))

        # CoreText requirement: Build out precise coordinate arrays explicitly
        # mapping base points AND the 4 standard OpenType phantom points
        # structurally.
        coords = [(0, 0)] * point_count

        # Map changes cleanly across targeted vector points
        for idx in right_side_indices:
            if idx < point_count:
                coords[idx] = (int_delta_width, 0)

        # CoreText requirement: Explicitly hand-compile the trailing 4
        # structural phantom points. [Left Side Bearing, Right Advance Width,
        # Top Side Bearing, Bottom Advance Height]
        coords.extend([(0, 0), (int_delta_width, 0), (0, 0), (0, 0)])

        new_var = TupleVariation(var.axes, coords)
        new_variations.append(new_var)

    if new_variations:
        gvar_table.variations[target_glyph_name] = new_variations
        # Fix maxp Table Bounds: Make sure CoreText allocates enough structural
        # memory to parse our injected variation maps.
        if "maxp" in font:
            maxp = font["maxp"]
            # Enforce that maxPoints matches or exceeds the raw geometry
            # constraints we added
            if hasattr(maxp, "maxPoints"):
                maxp.maxPoints = max(cast(int, maxp.maxPoints), point_count + 4)

        # Android's FreeType uses the HVAR table to track variable layout
        # bounds. Ensure our modified glyph links up to the same width delta
        # mapping index as the '0' character we are copying layout behaviors
        # from.
        if "HVAR" in font:
            hvar_table = font["HVAR"].table
            if hasattr(hvar_table, "VarIdxMap") and hvar_table.VarIdxMap is not None:
                # If '0' has a dedicated index mapping in the layout variations
                # store, point our new target glyph directly to that exact same
                # index link!
                if zero_glyph_name in hvar_table.VarIdxMap.mapping:
                    zero_metric_index = hvar_table.VarIdxMap.mapping[zero_glyph_name]
                    hvar_table.VarIdxMap.mapping[target_glyph_name] = zero_metric_index


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
    emdash_advance_width = hmtx_table[emdash_name][0]
    emdash_lsb = hmtx_table[emdash_name][1]

    hmtx_table["uni2588"] = (emdash_advance_width, emdash_lsb)
    hmtx_table["uni258C"] = (emdash_advance_width, emdash_lsb)
    hmtx_table["uni2590"] = (emdash_advance_width, emdash_lsb)

    # Map the variation matrices.
    if "gvar" in font and new_variations:
        gvar_table = font["gvar"]
        gvar_table.variations["uni2588"] = new_variations["skel_fill"]
        gvar_table.variations["uni258C"] = new_variations["skel_right"]
        gvar_table.variations["uni2590"] = new_variations["skel_left"]

        # Keep maxp limits safely aligned for iOS CoreText layout limits
        if "maxp" in font and hasattr(font["maxp"], "maxPoints"):
            max_pts = max(len(g.coordinates) for g in new_glyphs.values())
            font["maxp"].maxPoints = max(cast(int, font["maxp"].maxPoints), max_pts + 4)

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
        default=0.45,
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
            if font_path.is_file() and font_path.suffix.lower() in [".ttf", ".woff2"]:
                save_path = out_dir / font_path.name
                process_font(args, font_path, save_path)
    else:
        if input_font_path.suffix.lower() in [".ttf", ".woff2"]:
            save_path = (
                input_font_path.parent
                / f"{input_font_path.stem}_skeleton{input_font_path.suffix}"
            )
            process_font(args, input_font_path, save_path)


if __name__ == "__main__":
    main()
