# skeleton-fonts

Generate loading skeletons directly from fonts.

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

```
TODO insert example
```

### Fully rounded end-caps

```sh
uv run main.py fonts --corner-round 0.5
```

```
TODO insert example
```

### Thick skeleton

```sh
uv run main.py fonts --height-scale 0.95
```

```
TODO insert example
```


### Thin skeleton

```sh
uv run main.py fonts --height-scale 0.2 --corner-radius 0.5
```

```
TODO insert example
```

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

```
TODO insert example of loading block.
```

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