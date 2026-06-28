#!/usr/bin/env python3
"""
Static (offline) test of the server's CLIP detector + gate decision logic.

Feeds a directory of images through the EXACT server decision path
(config.load_config + AdBreakMonitor) in filename order — no HTTP, no live feed — and
reports:

  1. the frames where an uprise (context break) was detected,
  2. whether each uprise was ACCEPTED or BLOCKED by the active gate, and WHY it was
     blocked — the destination is an ad, or the previous segment was already content
     (the prev_window suppression), and
  3. a CLIP-similarity plot: green line = uprise accepted, red = blocked (destination is
     an ad), orange = blocked (previous segment was content).

The gate (none / clip) and every threshold — including the previous-window knobs
(prev_window / prev_gap) — come straight from Server/config.json, so this exercises
whatever the server is currently configured to do. Strictness defaults to the configured
level (exactly as the server treats a request with no strictness).

Usage:
    python3 static_test.py /path/to/frames
    python3 static_test.py /path/to/frames --strictness Aggressive --out run1.png
    python3 static_test.py /path/to/frames --stride 2   # every other frame (like the PoC)
"""

import os
import sys
import argparse

os.environ.setdefault("MPLBACKEND", "Agg")  # headless plotting; set before pyplot is imported
import matplotlib.pyplot as plt
from PIL import Image

# Reuse the real server logic (Server/ is a flat module dir, not a package).
SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Server")
sys.path.insert(0, SERVER_DIR)
from config import load_config              # noqa: E402
from ad_break_monitor import AdBreakMonitor  # noqa: E402

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
PHONE = "static-test"  # single synthetic stream id

# Gate verdict codes -> human-readable text for the report.
REASONS = {
    "accepted": "ACCEPTED",
    "dest_ad": "BLOCKED — destination is an ad",
    "prev_content": "BLOCKED — previous segment was content",
    "blocked": "BLOCKED by gate",
}


def gate_reason(accepted, last_gate):
    """
    Classify the gate's verdict on the latest boundary, using the attribution the monitor
    recorded on its per-phone state (AdBreakMonitor stashes `_PhoneState.last_gate`). No
    gate logic is re-derived here, so the report can never drift from the real decision.
    """
    if accepted:
        return "accepted"
    if last_gate and last_gate.get("blocked"):
        return "dest_ad"
    if last_gate and last_gate.get("prev_was_content"):
        return "prev_content"
    return "blocked"


def iter_frames(directory, stride=1):
    """
    Yield (name, PIL RGB image) for every `stride`-th image in `directory`, in filename
    order. stride=1 uses all frames; stride=2 keeps every other one, etc. — use it to
    subsample a folder dumped at a higher rate than the live client would send.
    """
    directory = os.path.expanduser(directory)
    if not os.path.isdir(directory):
        raise SystemExit(f"Not a directory: {directory}")
    names = sorted(n for n in os.listdir(directory) if n.lower().endswith(IMAGE_EXTS))
    if not names:
        raise SystemExit(f"No images ({', '.join(IMAGE_EXTS)}) found in {directory}")
    for name in names[::stride]:
        yield name, Image.open(os.path.join(directory, name)).convert("RGB")


def run(directory, strictness, stride):
    """
    Drive AdBreakMonitor over the folder; return (cfg, detector, uprises) where
    `uprises` is a list of (frame_name, frame_index, accepted_by_gate, reason_code).

    An uprise is detected when the detector appends a new boundary on a frame. The
    monitor's own return value tells us whether that uprise survived the gate (True =
    accepted, False = blocked); `reason_code` (see REASONS) is read from the monitor's
    per-phone attribution so a block is labelled destination-ad vs. previous-content.
    """
    cfg = load_config()
    cfg.debug.enabled = False  # silence the monitor's periodic logging; this script is the report
    monitor = AdBreakMonitor(cfg)
    st = monitor._get_state(PHONE)   # per-stream state: detector + last gate attribution
    detector = st.detector

    names, uprises, seen = [], [], 0
    for name, img in iter_frames(directory, stride):
        names.append(name)
        accepted = monitor.process_frame(PHONE, img, strictness)
        if len(detector.boundaries) > seen:  # a new uprise was flagged on this frame
            idx = detector.boundaries[-1]
            uprises.append((names[idx], idx, accepted, gate_reason(accepted, st.last_gate)))
            seen = len(detector.boundaries)
    return cfg, detector, uprises


def make_plot(detector, uprises, path):
    """
    CLIP similarity plot — green = accepted, red = blocked (destination is an ad),
    orange = blocked (previous segment was content), gray = blocked (other).
    """
    if not detector.history_frames:
        print("No frames were scored (folder smaller than the warm-up window) — no plot.")
        return None
    groups = [
        ("accepted",     "green",  "Uprise accepted"),
        ("dest_ad",      "red",    "Blocked — destination is an ad"),
        ("prev_content", "orange", "Blocked — previous segment was content"),
        ("blocked",      "gray",   "Blocked by gate"),
    ]

    fig = plt.figure(figsize=(15, 5))
    plt.plot(detector.history_frames, detector.history_raw,
             label="Raw similarity", color="lightblue", alpha=0.6)
    plt.plot(detector.history_frames, detector.history_smoothed,
             label="Smoothed (causal)", color="mediumblue", linewidth=2)
    for code, color, label in groups:
        marks = [idx for _, idx, _, why in uprises if why == code]
        for j, b in enumerate(marks):
            plt.axvline(b, color=color, linestyle="--", alpha=0.8,
                        label=label if j == 0 else None)
    plt.title("Static test — CLIP similarity & uprise decisions")
    plt.xlabel("Frame Index")
    plt.ylabel("Cosine Similarity")
    plt.legend(loc="lower right")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def report(cfg, detector, uprises, out_path):
    gate_on = cfg.gate_type != "none"
    print(f"\nScored {len(detector.history_frames)} frames | "
          f"gate: {cfg.gate_type} ({'active' if gate_on else 'off'})")

    if not uprises:
        print("\nNo uprises detected.")
    else:
        print(f"\n{len(uprises)} uprise(s):")
        w = max(len(n) for n, _, _, _ in uprises)
        for name, idx, accepted, code in uprises:
            verdict = REASONS[code] if gate_on else "ACCEPTED (no gate)"
            print(f"  {name.ljust(w)}  t={idx:<5}  {verdict}")
        if gate_on:
            acc = sum(1 for _, _, ok, _ in uprises if ok)
            prev = sum(1 for _, _, _, c in uprises if c == "prev_content")
            print(f"\n  {acc} accepted, {len(uprises) - acc} blocked by gate "
                  f"({prev} by the previous-window check)")

    saved = make_plot(detector, uprises, out_path)
    if saved:
        print(f"\nPlot saved -> {saved}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image_dir", help="directory of frames (processed in filename order)")
    p.add_argument("--strictness", default=None,
                   help="Weak / Balanced / Aggressive (default: config's default level)")
    p.add_argument("--out", default="static_test.png",
                   help="output PNG path (default: ./static_test.png)")
    p.add_argument("--stride", type=int, default=1,
                   help="process every Nth frame (default: 1 = all; 2 = every other, like the PoC)")
    args = p.parse_args(argv)
    if args.stride < 1:
        p.error("--stride must be >= 1")

    cfg, detector, uprises = run(args.image_dir, args.strictness, args.stride)
    report(cfg, detector, uprises, os.path.abspath(args.out))


if __name__ == "__main__":
    main()
