"""
make.fun bounty entry -- "WORLD BRIEF" daily front page, rendered to one PNG.

ENGINE + FINAL CONTENT.  Python 3.13, standard library only (os, struct,
zlib).  Deterministic by construction: no clock, no randomness, no float
arithmetic anywhere in the output path, no set/dict iteration order on any
drawing path, fixed zlib level 9, filter-0 scanlines, no ancillary PNG
chunks.  Two consecutive runs produce byte-identical files.

Sandbox contract:
    python3 -P -s /bot/main.py
    -> writes exactly one file: $MAKEFUN_OUTPUT_DIR/entry.png
       (falls back to ./output, creating the directory if missing)
    Output: 1024x1024 truecolor PNG, <= 1048576 bytes.

Composition (1024x1024, background PAPER #F2EDE2):
    Z0  date band   48,40 -> 976,168   INK fill, PAPER text
    Z1  story grid  48,192 -> 976,942  2 cols x 5 rows, row-major;
        each cell opens with a 10x132 field-colour edge bar at its origin
        (x=cx, y=cy+2, sharp corners), kicker FIELD:PLACE cap 28 at
        cx+24, headline lines cap 35 at cx+24, same cap bands as before
    Z2  divider     48,954 -> 976,956  2px MUTED
    Z3  ticker      48,966 -> 976,994  cap 28, MUTED, left-aligned
"""

import os
import struct
import zlib

# ============================================================================
#  CONTENT TABLE -- final copy.
#
#  Cell order is ROW-MAJOR: A1,B1,A2,B2,A3,B3,A4,B4,A5,B5.
#  Entry format: (field, place, headline_line_1, headline_line_2_or_None)
#  Ranks 1-6 carry two cap-35 headline lines; per the copy table A4 and
#  A5 also carry two lines, B4 carries one line only.
#  The tenth cell (field "ALSO") is the special "also today" panel:
#  MUTED bar, MUTED kicker, and two cap-28 item lines whose leading
#  10px dots are defined in ALSO_ITEMS below.
# ============================================================================

STORIES = [
    ("POLITICS", "CHINA",  "TRUMP AT APEC",  "XI PUTIN MEET"),   # A1  rank 1
    ("POLITICS", "KUWAIT", "IRAN STRIKES",   "GULF AIR BASE"),   # B1  rank 2
    ("ECONOMY",  "EU",     "KYIV LOAN PLAN", "REPARATIONS"),     # A2  rank 3
    ("POLITICS", "GAZA",   "ISRAEL CROSSES", "YELLOW LINE"),      # B2  rank 4
    ("POLITICS", "KERCH",  "KERCH BRIDGE",   "RAIL HIT AGAIN"),  # A3  rank 5
    ("CULTURE",  "NYC",    "VAN GOGH SETS",  "AUCTION RECORD"),  # B3  rank 6
    ("SCIENCE",  "SPACE",  "VOYAGER ONE",    "FARTHEST CRAFT"),  # A4  rank 7
    ("ECONOMY",  "DHAKA",  "WAGE PROTEST",   None),              # B4  rank 8
    ("SPORT",    "JOBURG", "LITTON DAS",     "TEST RECORD"),     # A5  rank 9
    ("ALSO",     "TODAY",  "HORMUZ TANKER",  "ART SETTLEMENT"),  # B5  rank 10 (special)
]

# The two item lines of the special B5 cell, with the field whose colour
# fills the 10px leading dot of each line.
ALSO_ITEMS = (
    ("HORMUZ TANKER", "POLITICS"),
    ("ART SETTLEMENT", "CULTURE"),
)

TICKER = "WORLD BRIEF:RANKED BY CONSEQUENCE"
DATE_KICKER = "WEDNESDAY · 2026-11-18 · WORLD BRIEF"
DATE_MAIN = "18 NOVEMBER 2026"

# ============================================================================
#  PALETTE -- flat fills only, no gradients, no AA, no dithering.
# ============================================================================

PAPER = (0xF2, 0xED, 0xE2)
INK = (0x1F, 0x1D, 0x1A)
MUTED = (0x6B, 0x67, 0x5C)
FIELD_COLORS = {
    "POLITICS": (0x2B, 0x58, 0x98),
    "ECONOMY": (0x2A, 0x6E, 0x3E),
    "SCIENCE": (0x17, 0x6D, 0x75),
    "DISASTER": (0xB2, 0x3A, 0x2E),
    "SPORT": (0xA9, 0x6E, 0x10),
    "CULTURE": (0x7A, 0x3F, 0x97),
}
ALSO_BAR_COLOR = MUTED  # neutral bar colour for the ALSO cell

W = H = 1024
CONTENT_W = 928

# ============================================================================
#  CANVAS PRIMITIVES (flat RGB bytearray)
# ============================================================================


def fill_rect(buf, x, y, w, h, rgb):
    if w <= 0 or h <= 0:
        return
    row = bytes(rgb) * w
    base = (y * W + x) * 3
    stride = W * 3
    for _ in range(h):
        buf[base:base + w * 3] = row
        base += stride


def set_pixel(buf, x, y, rgb):
    i = (y * W + x) * 3
    buf[i:i + 3] = bytes(rgb)


def fill_disc_px(buf, x, y, d, rgb):
    """d x d pixel disc, integer pixel-centre test, no floats."""
    for j in range(d):
        for i in range(d):
            if (2 * i + 1 - d) ** 2 + (2 * j + 1 - d) ** 2 <= d * d:
                set_pixel(buf, x + i, y + j, rgb)

# ============================================================================
#  TYPE -- hand-built 5x7 bitmap font, UPPERCASE ONLY, 42 glyphs total
#  (A-Z, 0-9, space, and the five marks · . : - /).  Drawn as filled unit
#  squares scaled by an integer S; cap height = 7*S.
#
#  Duospace advances in grid units (glyph width + 1 unit of tracking):
#      I and 1 -> 3 wide, advance 4
#      · . :   -> 2 wide, advance 3
#      space   -> advance 4 (nothing drawn, no tracking)
#      everything else -> 5 wide, advance 6   ("pitch = 5 glyph + 1 tracking")
#  No kerning, no hyphenation; lines are broken by the content table only
#  at spaces.
# ============================================================================

FONT = {
    "A": (
        ".###.",
        "#...#",
        "#...#",
        "#####",
        "#...#",
        "#...#",
        "#...#",
    ),
    "B": (
        "####.",
        "#...#",
        "#...#",
        "####.",
        "#...#",
        "#...#",
        "####.",
    ),
    "C": (
        ".####",
        "#....",
        "#....",
        "#....",
        "#....",
        "#....",
        ".####",
    ),
    "D": (
        "####.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "####.",
    ),
    "E": (
        "#####",
        "#....",
        "#....",
        "####.",
        "#....",
        "#....",
        "#####",
    ),
    "F": (
        "#####",
        "#....",
        "#....",
        "####.",
        "#....",
        "#....",
        "#....",
    ),
    "G": (
        ".####",
        "#....",
        "#....",
        "#..##",
        "#...#",
        "#...#",
        ".####",
    ),
    "H": (
        "#...#",
        "#...#",
        "#...#",
        "#####",
        "#...#",
        "#...#",
        "#...#",
    ),
    "I": (
        "###",
        ".#.",
        ".#.",
        ".#.",
        ".#.",
        ".#.",
        "###",
    ),
    "J": (
        "....#",
        "....#",
        "....#",
        "....#",
        "....#",
        "#...#",
        ".###.",
    ),
    "K": (
        "#...#",
        "#..#.",
        "#.#..",
        "##...",
        "#.#..",
        "#..#.",
        "#...#",
    ),
    "L": (
        "#....",
        "#....",
        "#....",
        "#....",
        "#....",
        "#....",
        "#####",
    ),
    "M": (
        "#...#",
        "##.##",
        "#.#.#",
        "#.#.#",
        "#...#",
        "#...#",
        "#...#",
    ),
    "N": (
        "#...#",
        "##..#",
        "#.#.#",
        "#..##",
        "#...#",
        "#...#",
        "#...#",
    ),
    "O": (
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "P": (
        "####.",
        "#...#",
        "#...#",
        "####.",
        "#....",
        "#....",
        "#....",
    ),
    "Q": (
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#..#.",
        "#.#..",
        ".##.#",
    ),
    "R": (
        "####.",
        "#...#",
        "#...#",
        "####.",
        "#.#..",
        "#..#.",
        "#...#",
    ),
    "S": (
        ".####",
        "#....",
        "#....",
        ".###.",
        "....#",
        "....#",
        "####.",
    ),
    "T": (
        "#####",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
    ),
    "U": (
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "V": (
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".#.#.",
        "..#..",
    ),
    "W": (
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#.#.#",
        "#.#.#",
        ".#.#.",
    ),
    "X": (
        "#...#",
        "#...#",
        ".#.#.",
        "..#..",
        ".#.#.",
        "#...#",
        "#...#",
    ),
    "Y": (
        "#...#",
        "#...#",
        ".#.#.",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
    ),
    "Z": (
        "#####",
        "....#",
        "...#.",
        "..#..",
        ".#...",
        "#....",
        "#####",
    ),
    "0": (
        ".###.",
        "#...#",
        "#..##",
        "#.#.#",
        "##..#",
        "#...#",
        ".###.",
    ),
    "1": (
        ".#.",
        "##.",
        ".#.",
        ".#.",
        ".#.",
        ".#.",
        "###",
    ),
    "2": (
        ".###.",
        "#...#",
        "....#",
        "...#.",
        "..#..",
        ".#...",
        "#####",
    ),
    "3": (
        "####.",
        "....#",
        "....#",
        ".###.",
        "....#",
        "....#",
        "####.",
    ),
    "4": (
        "...#.",
        "..##.",
        ".#.#.",
        "#..#.",
        "#####",
        "...#.",
        "...#.",
    ),
    "5": (
        "#####",
        "#....",
        "####.",
        "....#",
        "....#",
        "#...#",
        ".###.",
    ),
    "6": (
        ".###.",
        "#....",
        "#....",
        "####.",
        "#...#",
        "#...#",
        ".###.",
    ),
    "7": (
        "#####",
        "....#",
        "...#.",
        "..#..",
        "..#..",
        ".#...",
        ".#...",
    ),
    "8": (
        ".###.",
        "#...#",
        "#...#",
        ".###.",
        "#...#",
        "#...#",
        ".###.",
    ),
    "9": (
        ".###.",
        "#...#",
        "#...#",
        ".####",
        "....#",
        "....#",
        ".###.",
    ),
    "·": (
        "..",
        "..",
        "..",
        "##",
        "..",
        "..",
        "..",
    ),
    ".": (
        "..",
        "..",
        "..",
        "..",
        "..",
        "..",
        "##",
    ),
    ":": (
        "..",
        "..",
        "##",
        "..",
        "..",
        "##",
        "..",
    ),
    "-": (
        ".....",
        ".....",
        ".....",
        "#####",
        ".....",
        ".....",
        ".....",
    ),
    "/": (
        "....#",
        "...#.",
        "..#..",
        "..#..",
        ".#...",
        ".#...",
        "#....",
    ),
}

# space is the 42nd glyph: nothing drawn, fixed 4-grid-unit advance.


def _selfcheck_font():
    assert len(FONT) == 41, "font table must hold 41 drawn glyphs (+ space = 42)"
    for ch, rows in FONT.items():
        assert len(rows) == 7, (ch, len(rows))
        w = len(rows[0])
        for r in rows:
            assert len(r) == w, (ch, r)
            assert r.strip("#.") == "", (ch, r)
        if ch in ("I", "1"):
            assert w == 3, (ch, w)
        elif ch in ("·", ".", ":"):
            assert w == 2, (ch, w)
        else:
            assert w == 5, (ch, w)


_selfcheck_font()


def glyph_width(ch):
    """Glyph width in grid units (0 for space)."""
    if ch == " ":
        return 0
    return len(FONT[ch][0])


def glyph_advance(ch):
    """Pen advance in grid units: glyph width + 1 tracking (space = 4)."""
    if ch == " ":
        return 4
    return glyph_width(ch) + 1


def text_width(text, S, extra_units=0):
    """Rendered width in px; extra_units = added tracking per glyph."""
    if not text:
        return 0
    total = 0
    for ch in text:
        total += glyph_advance(ch) + extra_units
    last = text[-1]
    total = total - (glyph_advance(last) + extra_units) + glyph_width(last)
    return total * S


def draw_text(buf, text, x, y, S, rgb, extra_units=0):
    """Draw text with cap band top-left at (x, y). Cap height 7*S."""
    pen = x
    for ch in text:
        if ch != " ":
            rows = FONT[ch]
            for r, row in enumerate(rows):
                ty = y + r * S
                for c, cell in enumerate(row):
                    if cell == "#":
                        fill_rect(buf, pen + c * S, ty, S, S, rgb)
        pen += (glyph_advance(ch) + extra_units) * S

# ============================================================================
#  CONTENT VALIDATION -- budgets are enforced, not hoped for.
# ============================================================================

KICKER_BUDGET = 15   # chars, composed FIELD:PLACE
LINE_BUDGET = 14     # chars, each headline line
ITEM_BUDGET = 14     # chars, each ALSO item line
TICKER_BUDGET = 38   # chars

CELL_W, CELL_H = 448, 150
KICKER_X_OFF = 24    # kicker text column, right of the cell's colour bar
ITEM_X_OFF = 50      # ALSO item text column (dot column at KICKER_X_OFF)
BAR_W, BAR_H = 10, 132  # colour edge bar at the cell origin, y = cy + 2


def fail(msg):
    raise ValueError("entry content invalid: " + msg)


def check_string(text, budget, what, S, max_px, origin_px=0):
    for ch in text:
        if ch != " " and ch not in FONT:
            fail("%s uses %r, outside the 42-glyph charset: %r"
                 % (what, ch, text))
    if len(text) > budget:
        fail("%s is %d chars, budget is %d: %r"
             % (what, len(text), budget, text))
    wpx = text_width(text, S)
    if origin_px + wpx > max_px:
        fail("%s renders %dpx wide from origin %dpx, budget is %dpx: %r"
             % (what, wpx, origin_px, max_px, text))


def check_no_digits(text, what):
    for ch in text:
        if ch in "0123456789":
            fail("%s contains digit %r; digits are only allowed in the "
                 "date band: %r" % (what, ch, text))


def validate():
    if len(STORIES) != 10:
        fail("STORIES must hold exactly 10 entries, found %d" % len(STORIES))
    for i, (field, place, line1, line2) in enumerate(STORIES):
        rank = i + 1
        special = (field == "ALSO")
        if special:
            if i != 9:
                fail("the special ALSO cell must be the tenth cell (B5)")
            if line2 is None:
                fail("the special ALSO cell needs two item lines")
            if tuple(item for item, _ in ALSO_ITEMS) != (line1, line2):
                fail("ALSO_ITEMS must match the two item lines of the "
                     "ALSO cell, in order")
            for item, dot_field in ALSO_ITEMS:
                if dot_field not in FIELD_COLORS:
                    fail("ALSO item dot colour %r is not a field colour"
                         % (dot_field,))
                check_string(item, ITEM_BUDGET, "ALSO item line",
                             4, CELL_W, ITEM_X_OFF)
                check_no_digits(item, "ALSO item line")
        else:
            if field not in FIELD_COLORS:
                fail("story %d: unknown field %r" % (rank, field))
            if i < 6 and line2 is None:
                fail("story %d (rank 1-6) needs a second headline line"
                     % rank)
            check_string(line1, LINE_BUDGET,
                         "story %d headline line 1" % rank, 5, CELL_W,
                         KICKER_X_OFF)
            check_no_digits(line1, "story %d headline line 1" % rank)
            if line2 is not None:
                check_string(line2, LINE_BUDGET,
                             "story %d headline line 2" % rank, 5, CELL_W,
                             KICKER_X_OFF)
                check_no_digits(line2, "story %d headline line 2" % rank)
        kicker = field + ":" + place
        check_string(kicker, KICKER_BUDGET, "story %d kicker" % rank,
                     4, CELL_W, KICKER_X_OFF)
        check_no_digits(kicker, "story %d kicker" % rank)
    check_string(TICKER, TICKER_BUDGET, "ticker", 4, CONTENT_W)
    check_no_digits(TICKER, "ticker")
    check_string(DATE_KICKER, 64, "date-band kicker", 4, CONTENT_W)
    check_string(DATE_MAIN, 64, "date-band main line", 8, CONTENT_W)

# ============================================================================
#  LAYOUT
# ============================================================================


def draw_story_cell(buf, index, story):
    field, place, line1, line2 = story
    col, row = index % 2, index // 2
    cx = 48 + col * 480
    cy = 192 + row * 150
    special = (field == "ALSO")

    # full-height colour edge bar: 10x132 at the cell origin, sharp corners
    bar_color = ALSO_BAR_COLOR if special else FIELD_COLORS[field]
    fill_rect(buf, cx, cy + 2, BAR_W, BAR_H, bar_color)

    # kicker FIELD:PLACE, cap 28, at x=cx+24, cap band cy+14 -> cy+42
    kicker = field + ":" + place
    draw_text(buf, kicker, cx + KICKER_X_OFF, cy + 14, 4,
              MUTED if special else INK)

    if special:
        # two cap-28 item lines in the two headline cap bands; the 10px
        # dot column sits at cx+24, the item text starts at cx+50
        for (item, dot_field), band_y in zip(ALSO_ITEMS, (cy + 68, cy + 113)):
            fill_disc_px(buf, cx + KICKER_X_OFF, band_y + 9, 10,
                         FIELD_COLORS[dot_field])
            draw_text(buf, item, cx + ITEM_X_OFF, band_y, 4, INK)
    else:
        # headline, cap 35, at x=cx+24 (the kicker column);
        # line 1 band cy+68 -> cy+103, line 2 band cy+113 -> cy+148
        # (10px gap between cap bands)
        draw_text(buf, line1, cx + KICKER_X_OFF, cy + 68, 5, INK)
        if line2 is not None:
            draw_text(buf, line2, cx + KICKER_X_OFF, cy + 113, 5, INK)


def build_canvas():
    validate()
    buf = bytearray(W * H * 3)
    fill_rect(buf, 0, 0, W, H, PAPER)

    # Z0 date band: 48,40 -> 976,168, INK fill, PAPER text, centred on 512
    fill_rect(buf, 48, 40, 928, 128, INK)
    # band kicker, cap 28, +1 extra grid unit of tracking
    draw_text(buf, DATE_KICKER,
              512 - text_width(DATE_KICKER, 4, 1) // 2, 56, 4, PAPER, 1)
    # main line, cap 56, largest text on the canvas
    draw_text(buf, DATE_MAIN,
              512 - text_width(DATE_MAIN, 8) // 2, 96, 8, PAPER)

    # Z1 story grid: 48,192 -> 976,942, 2 columns x 5 rows, row-major
    for i, story in enumerate(STORIES):
        draw_story_cell(buf, i, story)

    # Z2 divider: 48,954 -> 976,956, 2px MUTED
    fill_rect(buf, 48, 954, 928, 2, MUTED)

    # Z3 ticker: one line, cap 28, left-aligned at x=48, band 966 -> 994
    draw_text(buf, TICKER, 48, 966, 4, MUTED)

    return buf

# ============================================================================
#  PNG WRITER -- IHDR, IDAT (zlib level 9), IEND only.  Colour type 2,
#  bit depth 8, filter 0 on every scanline, CRC32 on every chunk,
#  no ancillary chunks.
# ============================================================================


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def png_bytes(rgb_buf, w, h):
    stride = w * 3
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0 on every scanline
        raw.extend(rgb_buf[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def write_entry_png():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR") or os.path.join(".", "output")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "entry.png")
    data = png_bytes(build_canvas(), W, H)
    with open(path, "wb") as f:
        f.write(data)
    print("wrote %s (%d bytes)" % (path, len(data)))
    return path


if __name__ == "__main__":
    write_entry_png()
