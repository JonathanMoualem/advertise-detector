"""
Loads runtime tunables from a JSON file (default: Server/config.json).

Everything the ad-break detector needs to be tweaked without touching code lives here:
which gate to use (`gate_type`: "none" / "cnn" / "clip"), the CLIP streaming-detector
parameters, the CNN- and CLIP-gate definitions, and per-phone state housekeeping. A
partial or missing file still runs -- file values are merged over the built-in defaults
below (which mirror the CLIP PoC's defaults).
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
# gate behaviour confirmed with the user (suppress uprises that land on a graphic/commercial).
# File values override these.
_DEFAULTS = {
    # Which gate suppresses uprises: "none" / "cnn" / "clip". Left None here so an old
    # config that only sets the legacy `use_cnn_gate` flag still resolves correctly
    # (see load_config). A file that sets `gate_type` always wins.
    "gate_type": None,
    "use_cnn_gate": True,  # legacy on/off toggle, kept only for back-compat
    "clip": {
        "model_id": "openai/clip-vit-base-patch32",
        "past_window_size": 29,
        "smooth_window": 21,
        "min_ratio": 1.28,
        "stats_window": 120,
        "decision_smooth": 3,
        "cooldown": 60,
    },
    "gate": {
        "block_classes": ["Graphic", "Commercial"],
        "confidence_threshold": 0.5,
        "probe_after": 5,
    },
    "clip_gate": {
        "labels": [
            "A photo of a commercial on TV",
            "A photo of a TV broadcast that is not a commercial",
        ],
        "block_labels": ["A photo of a commercial on TV"],
        "confidence_threshold": 0.5,
        "probe_after": 5,
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
    model_id: str = "openai/clip-vit-base-patch32"
    past_window_size: int = 29
    smooth_window: int = 21
    min_ratio: float = 1.28
    stats_window: int = 120
    decision_smooth: int = 3
    cooldown: int = 60

    def detector_kwargs(self):
        """Kwargs forwarded verbatim to StreamingContextDetector (model_id excluded)."""
        return {
            "past_window_size": self.past_window_size,
            "smooth_window": self.smooth_window,
            "min_ratio": self.min_ratio,
            "stats_window": self.stats_window,
            "decision_smooth": self.decision_smooth,
            "cooldown": self.cooldown,
        }


@dataclass
class GateConfig:
    """
    CNN gate definition. An uprise is suppressed when the frames we just entered are
    (confidently, by majority) one of `block_classes` — i.e. a graphic or a commercial.
    `probe_after` is how many of the most recent frames define "what we're looking at now".
    """
    block_classes: List[str] = field(default_factory=lambda: ["Graphic", "Commercial"])
    confidence_threshold: float = 0.5
    probe_after: int = 5

    @property
    def blocked(self):
        """The set of class names that suppress an alert (uniform with ClipGateConfig)."""
        return set(self.block_classes)


@dataclass
class ClipGateConfig:
    """
    CLIP gate definition. Zero-shot CLIP matches each frame to one of `labels` (free-text
    descriptions); an uprise is suppressed when the frames we just entered are (confidently,
    by majority) one of `block_labels`. This mirrors GateConfig exactly — same
    `confidence_threshold` / `probe_after` semantics and the same `blocked` set contract —
    so the gate's majority-vote logic is identical regardless of which classifier feeds it.
    `block_labels` should be a subset of `labels` (entries not in `labels` simply never match).
    """
    labels: List[str] = field(default_factory=lambda: [
        "A photo of a commercial on TV",
        "A photo of a TV broadcast that is not a commercial",
    ])
    block_labels: List[str] = field(default_factory=lambda: ["A photo of a commercial on TV"])
    confidence_threshold: float = 0.5
    probe_after: int = 5

    @property
    def blocked(self):
        """The set of descriptions that suppress an alert (uniform with GateConfig)."""
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
    gate_type: str = "cnn"  # "none" / "cnn" / "clip"
    clip: ClipConfig = field(default_factory=ClipConfig)
    gate: GateConfig = field(default_factory=GateConfig)
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

    # Resolve the active gate. An explicit `gate_type` always wins; otherwise fall back to
    # the legacy boolean `use_cnn_gate` (True -> "cnn", False -> "none") so old configs work.
    gate_type = merged.get("gate_type")
    if gate_type is None:
        gate_type = "cnn" if bool(merged.get("use_cnn_gate", True)) else "none"
    gate_type = str(gate_type).strip().lower()
    if gate_type not in ("none", "cnn", "clip"):
        print(f"[config] Unknown gate_type {gate_type!r}; valid: none/cnn/clip. Using 'none'.")
        gate_type = "none"

    return AppConfig(
        gate_type=gate_type,
        clip=ClipConfig(**merged["clip"]),
        gate=GateConfig(**merged["gate"]),
        clip_gate=ClipGateConfig(**merged["clip_gate"]),
        strictness=StrictnessConfig(**merged["strictness"]),
        state=StateConfig(**merged["state"]),
        debug=DebugConfig(**merged["debug"]),
    )
