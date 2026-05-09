"""Sister banner for hammerstein-model — same family as the
hammerstein flagship banner (1536x592, navy / cream / rust / gold,
Didot italic). Updates wordmark to "Hammerstein-7B" and pillars
to PERSISTENT · DISTILLED · LOCAL — the three things this repo
ships.

Uses Pillow + freetype directly because Cairo's macOS toy text API
mis-handles "fr" ligatures (renders the letters apart while measuring
as if ligated)."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path("/Users/rayweiss/Desktop/Dev Work/hammerstein-model/docs/images/banner.png")

# Match flagship dimensions (the hammerstein/docs/images/banner.png)
WIDTH, HEIGHT = 1536, 592
SCALE = 2  # supersample, then downsize for crisp anti-aliased text
W, H = WIDTH * SCALE, HEIGHT * SCALE

# Palette — eyedropped from the flagship banner
NAVY = (28, 56, 92)        # #1c385c — deep navy bg
CREAM = (235, 224, 197)    # #ebe0c5 — warm cream wordmark
CREAM_SOFT = (210, 200, 175)  # tagline (slightly muted)
RUST = (170, 75, 50)       # #aa4b32 — [H] mark
GOLD = (180, 152, 95)      # #b4985f — pillars

DIDOT_ITALIC = "/System/Library/Fonts/Supplemental/Didot.ttc"
HOEFLER_ITALIC = "/System/Library/Fonts/Supplemental/Hoefler Text.ttc"
HELVETICA = "/System/Library/Fonts/Helvetica.ttc"

img = Image.new("RGB", (W, H), NAVY)
draw = ImageDraw.Draw(img)


def font(path, size, index=0):
    return ImageFont.truetype(path, size * SCALE, index=index)


def text_width(text, fnt):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0]


def draw_centered(text, fnt, y, color, letter_space=0):
    """y is the top of the text bounding box (in logical coords).
    Returns the drawn width."""
    if letter_space == 0:
        width = text_width(text, fnt)
        x = (W - width) // 2
        draw.text((x, y * SCALE), text, font=fnt, fill=color)
        return width
    # Manual letter-spacing for the pillars
    char_widths = [text_width(c, fnt) for c in text]
    total = sum(char_widths) + letter_space * SCALE * (len(text) - 1)
    x = (W - total) // 2
    for c, cw in zip(text, char_widths):
        draw.text((x, y * SCALE), c, font=fnt, fill=color)
        x += cw + letter_space * SCALE


def draw_wordmark(left, right, fnt_left, fnt_right, y, color_l, color_r, gap):
    """Draw [H] mark + wordmark, centered as a unit. y is top of bbox."""
    lw = text_width(left, fnt_left)
    rw = text_width(right, fnt_right)
    total = lw + gap * SCALE + rw
    x = (W - total) // 2
    draw.text((x, y * SCALE), left, font=fnt_left, fill=color_l)
    draw.text((x + lw + gap * SCALE, y * SCALE), right, font=fnt_right, fill=color_r)


# --- composition ----------------------------------------------------

# Top tagline: italic serif, light cream
tagline_font = font(HOEFLER_ITALIC, 38, index=2)  # Hoefler Text Italic
draw_centered(
    "The framework, distilled",
    tagline_font,
    y=85,
    color=CREAM_SOFT,
)

# Main wordmark: [H] in rust + "Hammerstein-7B" in cream, both Didot Italic
wordmark_font = font(DIDOT_ITALIC, 130, index=1)  # Didot Italic
draw_wordmark(
    left="[H]",
    right="Hammerstein-7B",
    fnt_left=wordmark_font,
    fnt_right=wordmark_font,
    y=235,
    color_l=RUST,
    color_r=CREAM,
    gap=24,
)

# Bottom pillars: caps, gold, letter-spaced
pillars_font = font(HELVETICA, 22)
draw_centered(
    "PERSISTENT  ·  DISTILLED  ·  LOCAL",
    pillars_font,
    y=465,
    color=GOLD,
    letter_space=4,
)

# Downsample for clean anti-aliased output at the target dimensions
img_final = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
OUT.parent.mkdir(parents=True, exist_ok=True)
img_final.save(OUT, optimize=True)
print(f"wrote {OUT} ({WIDTH}x{HEIGHT})")
