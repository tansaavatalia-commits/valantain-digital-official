"""Palette dei temi. Tutti i temi hanno sfondo chiaro: si stampano senza sprecare inchiostro."""

from __future__ import annotations

THEMES: dict[str, dict[str, str]] = {
    "minimal": {
        "label": "Minimal", "paper": "#FFFFFF", "ink": "#1F1F1F", "muted": "#7A7A7A",
        "line": "#D6D6D6", "accent": "#1F1F1F", "accent_soft": "#F1F1F1", "backdrop": "#E9E6E1",
    },
    "sage": {
        "label": "Sage", "paper": "#FFFFFF", "ink": "#2F3A2F", "muted": "#7D8A7A",
        "line": "#CFD8CC", "accent": "#6F8F6A", "accent_soft": "#EEF3EC", "backdrop": "#DCE5D8",
    },
    "blush": {
        "label": "Blush", "paper": "#FFFFFF", "ink": "#3D2B2E", "muted": "#9A7F83",
        "line": "#EBD3D6", "accent": "#C98A93", "accent_soft": "#FBF0F1", "backdrop": "#F2DDE0",
    },
    "ocean": {
        "label": "Ocean", "paper": "#FFFFFF", "ink": "#1E2C3A", "muted": "#6E8193",
        "line": "#CAD7E3", "accent": "#3F6E96", "accent_soft": "#EDF3F8", "backdrop": "#D5E2EE",
    },
    "terracotta": {
        "label": "Terracotta", "paper": "#FFFFFF", "ink": "#3A2A22", "muted": "#937B6E",
        "line": "#E6D2C6", "accent": "#C0714F", "accent_soft": "#FAF0EA", "backdrop": "#EFDCCF",
    },
    "lavender": {
        "label": "Lavender", "paper": "#FFFFFF", "ink": "#2E2A3D", "muted": "#857F99",
        "line": "#DAD5E8", "accent": "#8A7BB8", "accent_soft": "#F3F1F9", "backdrop": "#E3DEF0",
    },
}
