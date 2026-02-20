"""
ChargeGhost EVSE UI Color Palette
Consistent with e_mobility.qss
"""

# Primary Colors
ACCENT_TEAL = "#1EAD98"
ACCENT_TEAL_HOVER = "#17c9a8"
ACCENT_TEAL_PRESSED = "#159686"
ACCENT_TEAL_ALPHA = "rgba(30, 173, 152, 0.1)"

# Backgrounds
BG_MAIN = "#0d1117"
BG_SECONDARY = "#161b22"
BG_TERTIARY = "#21262d"
BG_HOVER = "#30363d"

# Borders
BORDER_DEFAULT = "#30363d"
BORDER_BRIGHT = "#484f58"

# Text
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED = "#6e7681"
TEXT_ON_ACCENT = "#0d1117"

# Status Colors
SUCCESS = "#238636"
SUCCESS_HOVER = "#2ea043"
SUCCESS_ALPHA = "rgba(35, 134, 54, 0.1)"

DANGER = "#da3633"
DANGER_HOVER = "#f85149"
DANGER_ALPHA = "rgba(218, 54, 51, 0.1)"

WARNING = "#f59e0b"
INFO = "#3b82f6"

# Log Colors (Unified)
LOG_COLORS = {
    "engine": WARNING,
    "ocpp": INFO,
    "ui": ACCENT_TEAL,
    "error": DANGER,
    "success": SUCCESS,
    "info": TEXT_SECONDARY,
    "verbose": TEXT_MUTED,
}
