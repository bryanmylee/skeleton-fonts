import argparse
import glob
from pathlib import Path
from fontTools.ttLib import TTFont


def sanitize_ps_name(name: str) -> str:
    """PostScript names cannot contain spaces or special characters."""
    return name.replace(" ", "")


def rename_font(font_path: Path, new_family: str, output_dir: Path):
    print(f"Processing: {font_path.name}")
    font = TTFont(font_path)
    name_table = font["name"]
    # Dynamically find the real weight string (e.g., "SemiBold", "Medium", "Black")
    # We check Typographic Subfamily (17) first, then fallback to Full Name (4) parsing
    style = name_table.getDebugName(17)

    if not style:
        full_name = name_table.getDebugName(4) or ""
        # If full name is "Inter 18pt SemiBold", we pull "SemiBold"
        for clean_word in [
            "Thin",
            "ExtraLight",
            "Light",
            "Regular",
            "Medium",
            "SemiBold",
            "Bold",
            "ExtraBold",
            "Black",
            "Italic",
        ]:
            if clean_word.lower() in full_name.lower():
                style = clean_word
                break

    if not style:
        style = name_table.getDebugName(2) or "Regular"

    # Handle composite styles safely (e.g., SemiBold Italic)
    if "Italic" in (name_table.getDebugName(2) or "") and "Italic" not in style:
        style = f"{style} Italic" if style != "Regular" else "Italic"

    # Build our standard naming tokens
    # Name ID 1 & 2 must adhere to the 4-base model if typographic fields (16/17) handle the rest
    is_ribbi = style in ["Regular", "Italic", "Bold", "Bold Italic"]

    # Core naming strings
    new_full_name = f"{new_family} {style}"
    new_ps_name = f"{sanitize_ps_name(new_family)}-{sanitize_ps_name(style)}"

    # Apply changes across all platforms/encodings
    for record in name_table.names:
        encoding = record.getEncoding()

        # ID 1: Font Family Name
        if record.nameID == 1:
            # If it's not a standard RIBBI style, OpenType says ID 1 should fallback to something safe
            # or keep it simple. For iOS/Expo, setting it to the base family works best when combined with 16.
            record.string = new_family.encode(encoding)

        # ID 2: Font Subfamily Name (Must map cleanly to RIBBI models)
        elif record.nameID == 2:
            if "Italic" in style and "Bold" in style:
                record.string = "Bold Italic".encode(encoding)
            elif "Bold" in style:
                record.string = "Bold".encode(encoding)
            elif "Italic" in style:
                record.string = "Italic".encode(encoding)
            else:
                record.string = "Regular".encode(encoding)

        # ID 3: Unique identifier
        elif record.nameID == 3:
            record.string = f"{new_ps_name};ExpoFix".encode(encoding)

        # ID 4: Full Font Name
        elif record.nameID == 4:
            record.string = new_full_name.encode(encoding)

        # ID 6: PostScript Name
        elif record.nameID == 6:
            record.string = new_ps_name.encode(encoding)

        # ID 16: Typographic Family Name (Crucial for advanced weight mapping)
        elif record.nameID == 16:
            record.string = new_family.encode(encoding)

        # ID 17: Typographic Subfamily Name (Where "Medium", "SemiBold" live safely)
        elif record.nameID == 17:
            record.string = style.encode(encoding)

    # Inject missing Typographic fields if they weren't in the original file
    # This guarantees iOS doesn't map Medium back to Regular.
    if not is_ribbi:
        name_table.setName(new_family, 16, 3, 1, 1033)  # Win / Unicode
        name_table.setName(style, 17, 3, 1, 1033)

    # Save the modified font
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / font_path.name

    if font_path.suffix.lower() == ".woff2":
        font.flavor = "woff2"
    font.save(output_path)
    print(f"  ↳ Saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch rename font family names using fontTools."
    )
    parser.add_argument(
        "glob_pattern",
        help="Glob pattern matching font files, e.g., 'fonts/Inter-*.ttf'",
    )
    parser.add_argument(
        "--family", required=True, help="New font family name, e.g., 'Inter'"
    )
    parser.add_argument(
        "--output", required=True, help="Output directory for renamed fonts"
    )

    args = parser.parse_args()

    # Resolve the glob pattern (recursive=True handles ** if used)
    font_files = glob.glob(args.glob_pattern, recursive=True)
    output_path = Path(args.output)

    if not font_files:
        print(f"No files matched the pattern: {args.glob_pattern}")
        return

    print(f"Found {len(font_files)} font files to process.")
    for file_str in font_files:
        file_path = Path(file_str)
        if file_path.suffix.lower() in (".ttf", ".otf", ".woff2"):
            try:
                rename_font(file_path, args.family, output_path)
            except Exception as e:
                print(f"  [ERROR] Failed to process {file_path.name}: {e}")
        else:
            print(f"Skipping non-font file: {file_path.name}")


if __name__ == "__main__":
    main()
