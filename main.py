import argparse
from enum import Enum
import fontforge
import os
from pathlib import Path
from typing import List, Literal, Tuple


class Quadrant(Enum):
    TopRight = 1
    TopLeft = 2
    BottomLeft = 3
    BottomRight = 4


Point = Tuple[float, float, bool]


def create_arc(
    x_center: float, y_center: float, radius: float, start_quadrant: Quadrant
) -> List[Point]:
    """
    Generates 3 points (start, control 1, control 2, end) for a 90-degree
    curve. Kapp (0.55228) calculates the perfect cubic bezier approximation of
    a circle.
    """
    kappa = 0.5522847498
    offset = radius * kappa

    if start_quadrant == Quadrant.TopRight:  # Moving from Top to Right
        return [
            (x_center, y_center + radius, True),
            (x_center + offset, y_center + radius, False),
            (x_center + radius, y_center + offset, False),
            (x_center + radius, y_center, True),
        ]
    elif start_quadrant == Quadrant.TopLeft:  # Moving from Left to Top
        return [
            (x_center - radius, y_center, True),
            (x_center - radius, y_center + offset, False),
            (x_center - offset, y_center + radius, False),
            (x_center, y_center + radius, True),
        ]
    elif start_quadrant == Quadrant.BottomLeft:  # Moving from Bottom to Left
        return [
            (x_center, y_center - radius, True),
            (x_center - offset, y_center - radius, False),
            (x_center - radius, y_center - offset, False),
            (x_center - radius, y_center, True),
        ]
    else:  # Moving from Right to Bottom
        return [
            (x_center + radius, y_center, True),
            (x_center + radius, y_center - offset, False),
            (x_center + offset, y_center - radius, False),
            (x_center, y_center - radius, True),
        ]


GlyphVariant = (
    Literal["block_fill"]
    | Literal["block_left"]
    | Literal["block_right"]
    | Literal["block_pill"]
)


def draw_skeleton_glyph(
    glyph,
    variant: GlyphVariant,
    width: float,
    height: float,
    y_offset: float,
    radius: float,
):
    """
    Draws outlines for fill, left cap, right cap, or standalone pill.
    """
    y_top = int(y_offset + (height / 2))
    y_bottom = int(y_offset - (height / 2))
    x_left = 0
    x_right = int(width)
    r = int(radius)

    # Magic constant for cubic Bezier approximation of a circle
    kappa = 0.5522847498
    offset = int(r * kappa)

    # Clear any existing drawings in the glyph's foreground layer safely
    glyph.clear()

    # Open the direct vector canvas drawing pen
    pen = glyph.glyphPen()

    if variant == "block_fill":
        pen.moveTo((x_left, y_top))
        pen.lineTo((x_right, y_top))
        pen.lineTo((x_right, y_bottom))
        pen.lineTo((x_left, y_bottom))
        pen.closePath()

    elif variant == "block_left":
        pen.moveTo((x_right, y_top))
        pen.lineTo((x_right, y_bottom))
        pen.lineTo((x_left + r, y_bottom))
        # Quadrant 3: Bottom to Left curve
        pen.qCurveTo(
            (x_left + r - offset, y_bottom),
            (x_left, y_bottom + r - offset),
            (x_left, y_bottom + r),
        )
        pen.lineTo((x_left, y_top - r))
        # Quadrant 2: Left to Top curve
        pen.qCurveTo(
            (x_left, y_top - r + offset),
            (x_left + r - offset, y_top),
            (x_left + r, y_top),
        )
        pen.closePath()

    elif variant == "block_right":
        pen.moveTo((x_left, y_top))
        pen.lineTo((x_right - r, y_top))
        # Quadrant 1: Top to Right curve
        pen.qCurveTo(
            (x_right - r + offset, y_top),
            (x_right, y_top - r + offset),
            (x_right, y_top - r),
        )
        pen.lineTo((x_right, y_bottom + r))
        # Quadrant 4: Right to Bottom curve
        pen.qCurveTo(
            (x_right, y_bottom + r - offset),
            (x_right - r + offset, y_bottom),
            (x_right - r, y_bottom),
        )
        pen.lineTo((x_left, y_bottom))
        pen.closePath()

    elif variant == "block_pill":
        pen.moveTo((x_left + r, y_top))
        pen.lineTo((x_right - r, y_top))
        # Quadrant 1: Top to Right
        pen.qCurveTo(
            (x_right - r + offset, y_top),
            (x_right, y_top - r + offset),
            (x_right, y_top - r),
        )
        pen.lineTo((x_right, y_bottom + r))
        # Quadrant 4: Right to Bottom
        pen.qCurveTo(
            (x_right, y_bottom + r - offset),
            (x_right - r + offset, y_bottom),
            (x_right - r, y_bottom),
        )
        pen.lineTo((x_left + r, y_bottom))
        # Quadrant 3: Bottom to Left
        pen.qCurveTo(
            (x_left + r - offset, y_bottom),
            (x_left, y_bottom + r - offset),
            (x_left, y_bottom + r),
        )
        pen.lineTo((x_left, y_top - r))
        # Quadrant 2: Left to Top
        pen.qCurveTo(
            (x_left, y_top - r + offset),
            (x_left + r - offset, y_top),
            (x_left + r, y_top),
        )
        pen.closePath()

    # Closing the pen automatically compiles and flushes the vector layers to the glyph
    pen = None

    # Correct path winding direction (TrueType requires specific clockwise/counter-clockwise flags)
    glyph.correctDirection()

    # Set character tracking widths
    glyph.width = x_right


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
        os.makedirs(f"{input_font_path}_skeleton", exist_ok=True)
        for font_path in input_font_path.iterdir():
            if font_path.is_file():
                save_path = (
                    f"{input_font_path}_skeleton/{font_path.stem}{font_path.suffix}"
                )
                process_font_file(args, font_path, save_path)
    else:
        save_path = f"{input_font_path.parent}/{input_font_path.stem}_skeleton{input_font_path.suffix}"
        process_font_file(args, input_font_path, save_path)


def process_font_file(args: argparse.Namespace, font_file: Path, save_path: str):
    try:
        font = fontforge.open(f"{font_file}")
    except Exception:
        return

    # Target character '0' (U+0030) to establish standard line context dimensions
    if 0x30 in font:
        zero_glyph = font[0x30]
        _, ymin, _, ymax = zero_glyph.boundingBox()
        ymin = float(ymin)
        ymax = float(ymax)
        zero_height = float(ymax - ymin)
        zero_width = float(zero_glyph.width)
    else:
        # Fallback values if target character '0' is missing
        ymin = float(font.baseline)
        ymax = float(font.ascent)
        zero_height = ymax - ymin
        zero_width = float(font.ascent) * 0.5

    # Compute custom scaling rules
    skel_height = zero_height * float(args.height_scale)
    skel_width = zero_width
    skel_y_center = float(ymin + ymax) / 2 + float(args.y_offset)
    skel_radius = skel_height * min(max(float(args.corner_round), 0.0), 0.5)

    print(f"Metrics mapped to baseline '0' height: {zero_height}")
    print(
        f"Generating Skeleton bars -> Width: {skel_width}, Height: {skel_height}, Corner Radius: {skel_radius}"
    )

    # Initialize glyph positions
    variants: List[GlyphVariant] = [
        "block_fill",
        "block_left",
        "block_right",
        "block_pill",
    ]
    for v in variants:
        font.createChar(-1, v)

    # Assign the master entry point to U+2588 (▌), U+258C (▌), and U+2590 (▐)
    font.createChar(0x2588, "uni2588")
    font.createChar(0x258C, "uni258c")
    font.createChar(0x2590, "uni2590")

    # Draw paths into glyph slots
    draw_skeleton_glyph(
        font["uni2588"],
        "block_fill",
        skel_width,
        skel_height,
        skel_y_center,
        skel_radius,
    )
    draw_skeleton_glyph(
        font["uni258c"],
        "block_right",
        skel_width,
        skel_height,
        skel_y_center,
        skel_radius,
    )
    draw_skeleton_glyph(
        font["uni2590"],
        "block_left",
        skel_width,
        skel_height,
        skel_y_center,
        skel_radius,
    )

    # Draw variants
    # for variant in variants:
    #     draw_skeleton_glyph(
    #         font[variant],
    #         variant,
    #         skel_width,
    #         skel_height,
    #         skel_y_center,
    #         skel_radius,
    #     )

    # TODO Should we fix this?
    # define_ligatures(font)

    font.generate(save_path)

    font.close()

    print(f"Success! Outputs created:\n - {save_path}")


def define_ligatures(font):
    """
    At this time, ligatures don't seem to work well for our use case.
    """
    # 1. Define our structural Glyph Classes
    # Class 0 is always reserved by FontForge for "any other glyph"
    # Class 1: All variants of spaces that act as boundaries
    # Class 2: The base skeleton block character
    whitespace_list = ["space", "nonbreakingspace", "thinspace", "uni00A0", "uni2009"]
    block_list = ["uni2588", "block_fill", "block_left", "block_right", "block_pill"]
    # 2. Package classes strictly as tuples of space-separated strings
    # Index 0 must be empty (the "magic" catch-all class for everything else)
    classes_tuple = (None, " ".join(whitespace_list), " ".join(block_list))

    # 2. Inject OpenType Substitution Rules (calt Feature)
    font.addLookup(
        "skel_calt_lookup",
        "gsub_contextchain",
        (),
        (("calt", (("latn", ("dflt")), ("grek", ("dflt")), ("cyrl", ("dflt")))),),
    )

    # Define single substitution steps inside context
    font.addLookup("skel_sub_fill", "gsub_single", (), ())
    font.addLookupSubtable("skel_sub_fill", "skel_sub_fill_sub")
    font["uni2588"].addPosSub("skel_sub_fill_sub", "block_fill")

    font.addLookup("skel_sub_left", "gsub_single", (), ())
    font.addLookupSubtable("skel_sub_left", "skel_sub_left_sub")
    font["uni2588"].addPosSub("skel_sub_left_sub", "block_left")

    font.addLookup("skel_sub_right", "gsub_single", (), ())
    font.addLookupSubtable("skel_sub_right", "skel_sub_right_sub")
    font["uni2588"].addPosSub("skel_sub_right_sub", "block_right")

    font.addLookup("skel_sub_pill", "gsub_single", (), ())
    font.addLookupSubtable("skel_sub_pill", "skel_sub_pill_sub")
    font["uni2588"].addPosSub("skel_sub_pill_sub", "block_pill")

    # 3. Apply Contextual Rules using Class-Based matching
    # Class 0 is "anything else" (including the absolute start/end of a line context)

    font.addContextualSubtable(
        "skel_calt_lookup",
        "skel_sub_fill",
        "class",
        "2 | 2 @<skel_sub_fill> | 2",
        bclasses=classes_tuple,
        mclasses=classes_tuple,
        fclasses=classes_tuple,
    )

    font.addContextualSubtable(
        "skel_calt_lookup",
        "skel_sub_left",
        "class",
        "1 | 2 @<skel_sub_left> | 2",
        bclasses=classes_tuple,
        mclasses=classes_tuple,
        fclasses=classes_tuple,
    )

    font.addContextualSubtable(
        "skel_calt_lookup",
        "skel_sub_right",
        "class",
        "2 | 2 @<skel_sub_right> | 1",
        bclasses=classes_tuple,
        mclasses=classes_tuple,
        fclasses=classes_tuple,
    )


if __name__ == "__main__":
    main()
