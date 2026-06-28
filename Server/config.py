"""
Loads runtime tunables from a JSON file (default: Server/config.json).

Everything the ad-break detector needs to be tweaked without touching code lives here:
whether to gate (`gate_type`: "none" / "clip"), the CLIP streaming-detector parameters,
the CLIP-gate definition, and per-phone state housekeeping. A partial or missing file
still runs -- file values are merged over the built-in defaults below (which mirror the
CLIP PoC's defaults).
"""

import copy
import json
import os
from dataclasses import dataclass, field
from typing import List

CONFIG_PATH = os.environ.get(
    "ADVERTISE_CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"),
)

# Built-in defaults. These mirror StreamingContextDetector's constructor defaults and the
# gate behaviour confirmed with the user (suppress uprises that land on a commercial, or
# whose previous segment was already content). File values override these.
_DEFAULTS = {
    # Whether to gate uprises: "none" / "clip". A file that sets `gate_type` always wins.
    "gate_type": "clip",
    "clip": {
        "model_id": "openai/clip-vit-base-patch32",
        "past_window_size": 29,
        "visual_smooth_window": 21,
        "min_ratio": 1.28,
        "reference_window": 120,
        "trigger_denoise_window": 3,
        "cooldown": 60,
    },
    "clip_gate": {
        "labels": [
            "A photo of a commercial on TV",
            "A photo of a TV broadcast that is not a commercial",
        ],
        "block_labels": ["A photo of a commercial on TV"],
        "confidence_threshold": 0.5,
        "probe_after": 5,
        "prev_window": 0,
        "prev_gap": 0,
    },
    "strictness": {
        "default": "Balanced",
        "ratios": {"Weak": 1.1, "Balanced": 1.2, "Aggressive": 1.3},
    },
    "state": {
        "idle_evict_minutes": 10,
    },
    "debug": {
        "enabled": True,
        "log_every": 30,
        "save_plot_on_stop": True,
        "plot_dir": "debug-plots",
    },
}


@dataclass
class ClipConfig:
    """
    Parameters for the CLIP streaming context detector (StreamingContextDetector).

    Each frame the detector scores the current frame's mean cosine similarity to the
    trailing `past_window_size` frames, then fires an "uprise" when that score jumps to at
    least `min_ratio` times its recent baseline. The three "window" knobs below each shape
    that decision differently — two are decision-critical, one is purely cosmetic:

      * reference_window        — the baseline the ratio is measured AGAINST. Decision-critical;
                                  also sets warm-up (no alert until it is half-full).
      * trigger_denoise_window  — smooths the score that goes INTO the ratio. Decision-critical;
                                  suppresses single-frame false triggers.
      * visual_smooth_window    — smooths a SEPARATE line for the diagnostic plots only. Has NO
                                  effect on the decision; removable without changing detection.
    """
    model_id: str = "openai/clip-vit-base-patch32"
    # How many trailing frames the current frame is compared against to form the raw score.
    past_window_size: int = 29
    # PLOT-ONLY: trailing window for the smoothed similarity line on the diagnostic graphs.
    # Never read by the boundary decision — purely cosmetic.
    visual_smooth_window: int = 21
    # Uprise trigger: fire when the de-noised score >= min_ratio * the reference-window median.
    # Higher = stricter (fewer alerts), lower = more sensitive.
    min_ratio: float = 1.28
    # Trailing window of raw scores whose median is the baseline the ratio divides by. Larger =
    # a slower, more stable "normal"; smaller = tracks recent content. Also gates warm-up: no
    # boundary can fire until this window is at least half-full (reference_window // 2 frames).
    reference_window: int = 120
    # Short trailing average of the score used as the ratio's numerator. 1 = use the raw current
    # score (no de-noising); higher = more robust to a single noisy frame, but slightly laggier.
    trigger_denoise_window: int = 3
    # Minimum number of frames between two ACCEPTED uprise flags. A gate-suppressed cross
    # does not start the cooldown, so it never blocks the next (possibly real) uprise.
    cooldown: int = 60

    def detector_kwargs(self):
        """Kwargs forwarded verbatim to StreamingContextDetector (model_id excluded)."""
        return {
            "past_window_size": self.past_window_size,
            "visual_smooth_window": self.visual_smooth_window,
            "min_ratio": self.min_ratio,
            "reference_window": self.reference_window,
            "trigger_denoise_window": self.trigger_denoise_window,
            "cooldown": self.cooldown,
        }


@dataclass
class ClipGateConfig:
    """
    CLIP gate definition. Zero-shot CLIP matches each frame to one of `labels` (free-text
    descriptions). An uprise is suppressed in TWO complementary cases:

      * DESTINATION — the most recent `probe_after` frames (the segment we just landed on)
        are (confidently, by majority) one of `block_labels` — i.e. we rose into an ad.
      * PREVIOUS    — the `prev_window` frames just BEFORE the uprise (skipping `prev_gap`
        frames at the cut) were confidently NOT a block_label — i.e. the previous segment
        was already content, so this uprise is a within-content change, not a return from a
        break. The previous window is `labels[-(probe_after + prev_gap + prev_window) :
        -(probe_after + prev_gap)]`. Set `prev_window = 0` to disable this check.

    `block_labels` should be a subset of `labels` (entries not in `labels` simply never match).
    """
    labels: List[str] = field(default_factory=lambda: [
        "A photo of a commercial on TV",
        "A photo of a TV broadcast that is not a commercial",
    ])
    block_labels: List[str] = field(default_factory=lambda: ["A photo of a commercial on TV"])
    confidence_threshold: float = 0.5
    probe_after: int = 5
    # Previous-window suppression: how many frames before the uprise to inspect (0 = off),
    # and how many frames to skip between the destination window and the previous window.
    prev_window: int = 0
    prev_gap: int = 0

    @property
    def blocked(self):
        """The set of descriptions that suppress an alert."""
        return set(self.block_labels)


@dataclass
class StrictnessConfig:
    """Maps the UI strictness level to the CLIP detector's min_ratio (the uprise trigger)."""
    default: str = "Balanced"
    ratios: dict = field(
        default_factory=lambda: {"Weak": 1.1, "Balanced": 1.2, "Aggressive": 1.3}
    )

    def ratio_for(self, level, fallback):
        """
        min_ratio for a strictness level. Falls back to the configured default level, then
        to `fallback` (clip.min_ratio) when the level and default are both unknown.
        """
        if level in self.ratios:
            return self.ratios[level]
        if self.default in self.ratios:
            return self.ratios[self.default]
        return fallback


@dataclass
class StateConfig:
    idle_evict_minutes: float = 10.0


@dataclass
class DebugConfig:
    enabled: bool = True          # debug instrumentation on by default
    log_every: int = 30           # log CLIP similarity stats every N scored frames
    save_plot_on_stop: bool = True  # write the diagnostic PNG when a session ends
    plot_dir: str = "debug-plots"   # where the PNGs go (resolved to an abs path at save time)


@dataclass
class AppConfig:
    gate_type: str = "clip"  # "none" / "clip"
    clip: ClipConfig = field(default_factory=ClipConfig)
    clip_gate: ClipGateConfig = field(default_factory=ClipGateConfig)
    strictness: StrictnessConfig = field(default_factory=StrictnessConfig)
    state: StateConfig = field(default_factory=StateConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)


def _deep_merge(base, override):
    """Recursively merge dict `override` onto a copy of dict `base`."""
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_config(path=CONFIG_PATH):
    """Read the JSON config (if present) merged over defaults, into a typed AppConfig."""
    raw = {}
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh) or {}
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[config] Could not read {path} ({exc}); using defaults.")
            raw = {}
    else:
        print(f"[config] No config file at {path}; using defaults.")

    merged = _deep_merge(_DEFAULTS, raw)

    # Resolve the active gate. Only "none" / "clip" are valid (the CNN gate was removed);
    # anything else falls back to "none" so a stale config never silently mis-gates.
    gate_type = str(merged.get("gate_type", "clip")).strip().lower()
    if gate_type not in ("none", "clip"):
        print(f"[config] Unknown gate_type {gate_type!r}; valid: none/clip. Using 'none'.")
        gate_type = "none"

    return AppConfig(
        gate_type=gate_type,
        clip=ClipConfig(**merged["clip"]),
        clip_gate=ClipGateConfig(**merged["clip_gate"]),
        strictness=StrictnessConfig(**merged["strictness"]),
        state=StateConfig(**merged["state"]),
        debug=DebugConfig(**merged["debug"]),
    )
