"""Adam's orb: a glowing sphere whose colour and motion show what Adam is doing.

Frames are drawn once with numpy (at 2x, then downsampled for smooth edges) and
cycled by the window, so the animation costs almost nothing while it runs.
"""
from functools import lru_cache

import numpy as np
from PIL import Image

FRAMES = 24

# state: (shell colour, core colour, glow colour, breathe amount, strand strength, spin speed)
STATES = {
    "idle":      ((6, 28, 90),   (120, 210, 255), (30, 110, 255), 0.025, 0.7, 1),
    "listening": ((0, 60, 72),   (170, 255, 240), (0, 225, 255),  0.06,  0.9, 2),
    "thinking":  ((40, 12, 100), (225, 190, 255), (150, 80, 255), 0.03,  1.4, 3),
    "speaking":  ((4, 50, 100),  (200, 240, 255), (50, 190, 255), 0.07,  1.0, 2),
    "waiting":   ((90, 42, 0),   (255, 225, 160), (255, 160, 20), 0.045, 0.9, 1),
    "error":     ((90, 8, 20),   (255, 190, 190), (255, 50, 75),  0.02,  0.7, 1),
}


@lru_cache(maxsize=4)
def _grid(n):
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    dx, dy = (x - c) / c, (y - c) / c
    return dx, dy, np.sqrt(dx * dx + dy * dy), np.arctan2(dy, dx)


def render(state, t, size, bg):
    """One RGB frame of the orb for state at phase t (0..1), composited on colour bg."""
    shell, core, glow, breathe, strands, spin = STATES[state]
    shell, core, glow = (np.array(c, np.float32) for c in (shell, core, glow))
    n = size * 2
    dx, dy, r, ang = _grid(n)
    wave = np.sin(2 * np.pi * t)

    radius = 0.5 * (1 + breathe * wave)
    inside = np.clip((radius - r) * n * 0.5, 0, 1)[..., None]   # anti-aliased edge
    rr = np.clip(r / radius, 0, 1)

    # Dark shell, bright energy core, glowing strands that turn with the state's speed.
    heart = np.exp(-(rr / (0.42 + 0.06 * wave)) ** 2)
    arms = np.sin(3 * (ang + 2.4 * rr) - 2 * np.pi * spin * t)       # spiral arms
    shimmer = 0.6 + 0.4 * np.sin(5 * rr - 2 * np.pi * t)
    strand = np.clip(arms, 0, 1) ** 4 * shimmer * rr * (1 - rr) * 4 * strands
    rim = np.clip((rr - 0.78) / 0.22, 0, 1) ** 2
    light = np.clip(heart + strand * 0.8, 0, 1)[..., None]
    color = shell * (1 - light) + core * light + glow * (rim[..., None] * 0.85 + strand[..., None] * 0.35)

    # Small glassy highlight, upper left.
    hx, hy = dx / radius + 0.42, dy / radius + 0.48
    color = color + 200 * (np.exp(-(hx * hx + hy * hy) / 0.018) * 0.5)[..., None]

    # Soft halo, plus a faint ring drifting outward.
    halo = np.exp(-np.clip(r - radius, 0, None) / 0.13) * (0.5 + 0.12 * wave)
    ring = np.exp(-((r - radius - 0.04 - 0.34 * t) / 0.012) ** 2) * 0.3 * (1 - t)
    # HUD: a broken ring turning one way and a ring of ticks turning the other.
    arcs = np.exp(-((r - 0.84) / 0.012) ** 2) * (np.sin(4 * ang - 2 * np.pi * t) > 0.35) * 0.55
    ticks = np.exp(-((r - 0.93) / 0.02) ** 2) * np.clip(np.sin(60 * ang + 2 * np.pi * t), 0, 1) ** 6 * 0.35
    bgc = np.array(bg, np.float32)
    outside = bgc + (halo + ring + arcs + ticks)[..., None] * glow

    img = outside * (1 - inside) + np.clip(color, 0, 255) * inside
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").resize((size, size), Image.LANCZOS)


def frames(state, size, bg):
    return [render(state, i / FRAMES, size, bg) for i in range(FRAMES)]
