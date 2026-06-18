"""Brake visual design tokens for the PyQt GUI.

The source design system lives in:
Design Elements/Brake Design System/colors_and_type.css

Keep this module presentation-only. App behavior belongs in controller/state code.
"""
from __future__ import annotations

from pathlib import Path


class Colors:
    base = "#0b0e14"
    surface_1 = "#12161f"
    surface_2 = "#181d28"
    surface_3 = "#212736"
    surface_sink = "#080a0f"

    border = "rgba(243, 240, 230, 0.09)"
    border_strong = "rgba(243, 240, 230, 0.16)"
    border_faint = "rgba(243, 240, 230, 0.05)"

    fg_1 = "#f3f0e6"
    fg_2 = "#c2c6cf"
    fg_3 = "#8f96a3"
    fg_4 = "#5b626f"
    on_accent = "#1a140a"

    gold = "#e6cd9b"
    gold_bright = "#f0dcb0"
    gold_dim = "#c4ab78"
    gold_soft = "rgba(230, 205, 155, 0.14)"
    gold_line = "rgba(230, 205, 155, 0.32)"

    teal = "#5eead4"
    teal_deep = "#14b8a6"
    teal_soft = "rgba(94, 234, 212, 0.13)"
    teal_line = "rgba(94, 234, 212, 0.30)"

    amber = "#ffb454"
    amber_soft = "rgba(255, 180, 84, 0.14)"
    amber_line = "rgba(255, 180, 84, 0.32)"

    coral = "#e2796b"
    coral_soft = "rgba(226, 121, 107, 0.13)"
    coral_line = "rgba(226, 121, 107, 0.32)"

    lock_blue = "#6ba6e0"
    lock_soft = "rgba(107, 166, 224, 0.14)"
    lock_line = "rgba(107, 166, 224, 0.34)"


class Type:
    sans = '"Geist", "Segoe UI Variable", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
    mono = '"Geist Mono", "Cascadia Code", "Consolas", monospace'

    display = 30
    h1 = 22
    h2 = 17
    h3 = 14
    body = 14
    sm = 13
    xs = 12
    micro = 11

    regular = 400
    medium = 500
    semi = 560
    bold = 680


class Space:
    x1 = 4
    x2 = 8
    x3 = 12
    x4 = 16
    x5 = 20
    x6 = 24
    x8 = 32
    x10 = 40
    x12 = 48
    x16 = 64


class Radius:
    xs = 4
    sm = 6
    md = 9
    lg = 12
    xl = 16


def qss_path() -> Path:
    """Path to the app-wide Brake Qt stylesheet."""
    return Path(__file__).with_name("brake.qss")
