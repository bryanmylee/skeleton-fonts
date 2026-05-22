<img width="960" height="124" alt="title" src="https://github.com/user-attachments/assets/8eb55c51-fa92-44d8-b265-3410bfd53fa6" />

# skeleton-fonts

Generate loading skeletons from your fonts.

`skeleton-fonts` modifies a font’s block characters (`▐` / `█` / `▌`) to create
loading skeleton placeholders that naturally match text layout, including
dynamic line height, variable-width fonts, and custom typography.

Instead of approximating text dimensions with divs, overlays, or manually tuned
skeleton components, `skeleton-fonts` embeds skeleton rendering behavior
directly into the font itself.

The result is loading placeholders that match real text metrics exactly
**without layout shift**.

## Features

- ✨ Font-native loading skeletons
- 📏 Exact line-height matching
- ↔️ Variable-width font support
- 🔄 Zero layout shift when content loads
- ⭕ Rounded end caps
- 🎚 Adjustable skeleton visual height
- 🧩 Configurable border radius
- 🎨 Works with existing typography systems
- ⚡ No runtime measurement required

## Usage

[`uv`](https://docs.astral.sh/uv/) is used to manage project dependencies.

```sh
uv sync
```

Run `uv run main.py --help` to view argument and configuration options.

## Examples

Given a directory `fonts` containing font files.

### Default skeleton

```sh
uv run main.py fonts
```

<img width="932" height="308" alt="demo-default" src="https://github.com/user-attachments/assets/08e36a49-5dfa-464e-a95f-3855feaf7a32" />

### Fully rounded end-caps

```sh
uv run main.py fonts --corner-round 0.5
```

<img width="932" height="308" alt="demo-corner-0 5" src="https://github.com/user-attachments/assets/76118be3-27e8-4c34-9cd6-78e709ac6b2f" />

### Thick skeleton

```sh
uv run main.py fonts --height-scale 0.95
```

<img width="932" height="308" alt="demo-height-0 95" src="https://github.com/user-attachments/assets/bbb25cba-6207-4332-ae85-35939b142c48" />

### Thin skeleton

```sh
uv run main.py fonts --height-scale 0.2 --corner-radius 0.5
```

<img width="932" height="308" alt="demo-height-0 2-corner-0 5" src="https://github.com/user-attachments/assets/ad20a2ce-5556-4e0a-ab79-7235d9ce6db4" />

## Why?

Traditional text skeletons are usually built with boxes:

```tsx
<Skeleton width={120} height={20} />
```

This does not work easily with dynamic typography, requiring complex logic to
match line heights or measure content sizes after render.

Without careful fine-tuning, small metric differences can cause loading states
to shift when content appears.

`skeleton-fonts` solves this by tying skeleton geometry directly to font
metrics. Implementing a text skeleton is as simple as:

```tsx
<Text>
  {data.isLoading ? "▐████████▌" : data.name}
</Text>
```

Because the skeleton exists inside the font:

- Line height matches automatically
- Leading is preserved exactly
- Variable-width text flows naturally
- No measuring text dimensions
- No manual tuning
- No layout shift

## How it works

`skeleton-fonts` modifies Unicode block characters:

```text
▐████████████▌
```

These glyphs are reshaped into skeleton primitives:

- `▐` → left rounded cap
- `█` → fill body
- `▌` → right rounded cap

The block above renders as:

<img width="702" height="88" alt="demo-render" src="https://github.com/user-attachments/assets/fdb5cfac-fc6c-4bcd-88a0-d10c9f6fe69b" />

Because glyph dimensions come from the font itself, placeholders inherit typography metrics automatically.

## Inspiration

The ideal loading state should preserve layout perfectly and require no
additional engineering effort. After trying and failing to fine-tune skeleton
boxes to match my text line heights at every size for every font, I decided to
put the skeleton directly into the font itself.

`skeleton-fonts` exists to make that easy.

## Status

Early project. Feedback, issues, and contributions are welcome.

---

Built for developers who care about typography, performance, and eliminating layout shift.
