"""Duration planning — word budgets per target, real timing from narration audio."""
from __future__ import annotations

WPM = 150  # conversational documentary narration

DURATIONS = {
    "8-10": {"min_s": 480, "max_s": 600, "target_s": 540, "words": 1350, "scenes": (8, 12)},
    "12-15": {"min_s": 720, "max_s": 900, "target_s": 810, "words": 2000, "scenes": (12, 18)},
    "15-20": {"min_s": 900, "max_s": 1200, "target_s": 1050, "words": 2600, "scenes": (15, 22)},
    "auto": {"min_s": 480, "max_s": 1200, "target_s": 810, "words": 2000, "scenes": (10, 18)},
}


def plan_for(duration: str) -> dict:
    return DURATIONS.get(duration, DURATIONS["auto"])


def estimate_text_seconds(text: str) -> float:
    return max(1.0, len(text.split()) / WPM * 60)
