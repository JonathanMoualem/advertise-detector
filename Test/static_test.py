#!/usr/bin/env python3
"""
Static (offline) test of the server's CLIP detector + gate decision logic.

Feeds a directory of images through the EXACT server decision path
(config.load_config + AdBreakMonitor) in filename order — no HTTP, no live feed — and
reports:

  1. the frames where an uprise (context break) was detected,
  2. whether each uprise was ACCEPTED or BLOCKED by the active gate, and
  3. a CLIP-similarity plot: green line = uprise accepted, red line = uprise blocked
     by the gate.

The gate (none / cnn / clip) and every threshold come straight from Server/config.json,
so this exercises whatever the server is currently configured to do. Strictness defaults
to the configured level (exactly as the server treats a request with no strictness).

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
    `uprises` is a list of (frame_name, frame_index, accepted_by_gate).

    An uprise is detected when the detector appends a new boundary on a frame. The
    monitor's own return value tells us whether that uprise survived the gate: True =
    accepted (alert), False on a boundary frame = blocked by the gate.
    """
    cfg = load_config()
    cfg.debug.enabled = False  # silence the monitor's periodic logging; this script is the report
    monitor = AdBreakMonitor(cfg)
    detector = monitor._get_state(PHONE).detector  # the per-stream CLIP detector

    names, uprises, seen = [], [], 0
    for name, img in iter_frames(directory, stride):
        names.append(name)
        accepted = monitor.process_frame(PHONE, img, strictness)
        if len(detector.boundaries) > seen:  # a new uprise was flagged on this frame
            idx = detector.boundaries[-1]
            uprises.append((names[idx], idx, accepted))
            seen = len(detector.boundaries)
    return cfg, detector, uprises


def make_plot(detector, uprises, path):
    """CLIP similarity plot — green line = uprise accepted, red line = blocked by gate."""
    if not detector.history_frames:
        print("No frames were scored (folder smaller than the warm-up window) — no plot.")
        return None
    accepted = [idx for _, idx, ok in uprises if ok]
    blocked = [idx for _, idx, ok in uprises if not ok]

    fig = plt.figure(figsize=(15, 5))
    plt.plot(detector.history_frames, detector.history_raw,
             label="Raw similarity", color="lightblue", alpha=0.6)
    plt.plot(detector.history_frames, detector.history_smoothed,
             label="Smoothed (causal)", color="mediumblue", linewidth=2)
    for j, b in enumerate(accepted):
        plt.axvline(b, color="green", linestyle="--", alpha=0.8,
                    label="Uprise accepted" if j == 0 else None)
    for j, b in enumerate(blocked):
        plt.axvline(b, color="red", linestyle="--", alpha=0.8,
                    label="Uprise blocked by gate" if j == 0 else None)
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
        w = max(len(n) for n, _, _ in uprises)
        for name, idx, accepted in uprises:
            verdict = ("ACCEPTED" if accepted else "BLOCKED by gate") if gate_on \
                else "ACCEPTED (no gate)"
            print(f"  {name.ljust(w)}  t={idx:<5}  {verdict}")
        if gate_on:
            acc = sum(1 for _, _, ok in uprises if ok)
            print(f"\n  {acc} accepted, {len(uprises) - acc} blocked by gate")

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
