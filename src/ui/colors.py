# Exact colors extracted from user's color palette image (Photoshop-validated HEX).
# Used as the single source of truth for the entire UI.

C1_PALE_CREAM = "#F3E2DB"   # 243,226,219 - warm off-white
C2_WARM_GRAY = "#B1A096"    # 177,160,150 - muted warm gray
C3_OCHRE = "#C29051"        # 194,144,81 - mustard / amber
C4_SALMON = "#D59C6F"       # 213,156,111 - warm peach
C5_LIGHTEST_PINK = "#FDECE2"  # 253,236,226 - lightest cream-pink
C6_BURGUNDY = "#460008"     # 70,0,8 - deep wine
C7_NEAR_BLACK = "#070304"   # 7,3,4 - near-black with warm undertone

# Accents extracted from user's UI reference (image 2)
ACCENT_GOLD = "#D0A372"     # primary warm highlight (close to C3 but lighter)
ACCENT_RUST = "#B36953"     # secondary terracotta accent (lighter than C6)

# Dark theme derived colors (built around C7)
BG_BASE = "#0C0A08"         # primary window background (warm black)
BG_PANEL = "#141311"        # card / panel background
BG_PANEL_HOVER = "#1A1816"  # panel hover
BG_PANEL_PRESSED = "#221F1C"  # panel pressed
BG_INPUT = "#0F0D0B"        # input field background
BG_RAISED = "#1F1C18"       # raised / elevated
DIVIDER = "#26221E"         # subtle divider
DIVIDER_STRONG = "#3A342E"  # stronger divider
BORDER = "#2A2622"          # border color

# Text colors
TEXT_PRIMARY = C1_PALE_CREAM
TEXT_SECONDARY = C2_WARM_GRAY
TEXT_MUTED = "#7A726A"      # darker muted text
TEXT_DISABLED = "#4A4540"
TEXT_INVERT = C7_NEAR_BLACK  # dark text on light/accent backgrounds
TEXT_ACCENT = ACCENT_GOLD

# Semantic
SUCCESS = "#7FB069"         # soft sage
WARNING = C4_SALMON
ERROR = "#C9484B"           # muted red (close to ACCENT_RUST)
INFO = ACCENT_GOLD

# Selection / focus
SELECTION_BG = "rgba(208, 163, 114, 38)"  # ACCENT_GOLD @ 15%
SELECTION_BORDER = ACCENT_GOLD
FOCUS_RING = ACCENT_GOLD

# Shadow / overlay
SHADOW = "rgba(0, 0, 0, 180)"
OVERLAY = "rgba(12, 10, 8, 200)"
