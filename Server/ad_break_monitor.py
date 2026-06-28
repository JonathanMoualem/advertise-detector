"""
AdBreakMonitor — the alert decision core.

CLIP scene/context detection is the PRIMARY decision maker: the streaming detector flags
the moment a broadcast enters a stable / repetitive segment (an "uprise" in self-similarity
to the recent past), which is a strong proxy for "the show is back" after an ad break.

An OPTIONAL CLIP gate (config `gate_type`: "none" / "clip") suppresses an uprise in two
complementary cases, so an alert only fires on a genuine ad -> content return:

  * DESTINATION — the frames we just landed on are a commercial rather than real content
    (e.g. an uprise into a long, stable commercial), or
  * PREVIOUS    — the segment just before the uprise was already content, so the uprise is a
    within-content change (two different-looking parts of the same show), not a return.

The gate is backed by ClipGateClassifier: zero-shot CLIP matching each frame to free-text
descriptions, exposing classify(img) -> (label, certainty). When the gate is ON the classifier
runs once PER FRAME on arrival and its label is cached, so a boundary decision only reads
pre-computed labels — there is no burst of inference at decision time.

State is kept PER PHONE NUMBER, because the temporal CLIP windows assume one continuous
stream; mixing two viewers' frames into one detector would be wrong.
"""

import os
import re
import threading
import time
from collections import deque

from clip_context_detector import (
    StreamingContextDetector,
    setup_clip_model,
    _pick_torch_device,
)
from clip_gate import ClipGateClassifier


class _PhoneState:
    """Per-stream detector + (when gating) a rolling buffer of per-frame CLIP labels."""

    def __init__(self, detector, label_maxlen):
        self.detector = detector
        # (class_name, certainty) per frame, newest on the right; aligned 1:1 with the
        # detector's rolling embedding buffer so window slices line up.
        self.labels = deque(maxlen=label_maxlen) if label_maxlen else None
        # Why the gate accepted/suppressed the MOST RECENT boundary, as
        # {"blocked": bool, "prev_was_content": bool}. Lets offline tools (static_test)
        # attribute a decision without re-deriving the gate logic. None until the first
        # boundary is gated.
        self.last_gate = None
        self.last_seen = time.time()
        self.lock = threading.Lock()


class AdBreakMonitor:
    def __init__(self, config, clip_model=None, clip_processor=None):
        self.cfg = config
        self.debug = config.debug
        self.gate_type = config.gate_type          # "none" / "clip"
        self.use_gate = self.gate_type != "none"
        self.device = _pick_torch_device()

        # CLIP model + processor are shared across all phones (read-only at inference) and,
        # when the CLIP gate is active, shared with the gate classifier too — so enabling
        # the CLIP gate loads no extra model.
        if clip_model is None or clip_processor is None:
            clip_model, clip_processor = setup_clip_model(
                model_id=config.clip.model_id, device=self.device
            )
        self.clip_model = clip_model
        self.clip_processor = clip_processor

        # Build the CLIP gate classifier + its config when gating is on. _gate_pass / _majority
        # only ever read self._gate_cfg (probe_after, confidence_threshold, prev_window,
        # prev_gap, blocked), reusing the CLIP model already loaded above — no extra model.
        self._classifier = None
        self._gate_cfg = None
        self._blocked = set()
        if self.gate_type == "clip":
            self._classifier = ClipGateClassifier(
                self.clip_model, self.clip_processor,
                labels=config.clip_gate.labels, device=self.device,
            )
            self._gate_cfg = config.clip_gate
            # Labels that should suppress an alert (we landed on an ad, not content).
            self._blocked = self._gate_cfg.blocked

        self._phones = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public

    def process_frame(self, phone_number, img, strictness=None):
        """
        Ingest one frame (PIL RGB) for `phone_number`. Returns True iff this frame should
        fire a "show is back" alert.

        `strictness` (e.g. "Weak"/"Balanced"/"Aggressive") sets the CLIP uprise trigger
        (min_ratio) live, falling back to clip.min_ratio when unknown.
        """
        self._evict_idle()
        st = self._get_state(phone_number)

        with st.lock:
            st.last_seen = time.time()

            # Strictness drives the trigger threshold, applied immediately (per frame) so a
            # mid-session change takes effect without restarting capture.
            st.detector.min_ratio = self.cfg.strictness.ratio_for(
                strictness, self.cfg.clip.min_ratio
            )

            # Gate ON: classify NOW (one inference) and cache, so the boundary branch is free.
            if self.use_gate:
                class_name, certainty = self._classifier.classify(img)
                st.labels.append((class_name, certainty))

            result = st.detector.process_frame(img)

            if self.debug.enabled:
                self._debug_periodic(phone_number, st, result)

            if result is None or not result.is_boundary:
                return False

            if not self.use_gate:
                accepted = True  # pure CLIP mode: every uprise alerts
                if self.debug.enabled:
                    self._log(f"[{phone_number}] BOUNDARY @t={result.frame_index} "
                              f"ratio={result.ratio:.3f} -> ALERT (gate off)")
            else:
                accepted = self._gate_pass(st, phone_number, result)

            # Arm the cooldown only on an ACCEPTED cross, so a gate-suppressed uprise does
            # not block the next, possibly real, one.
            if accepted:
                st.detector.confirm_boundary(result.frame_index)
            return accepted

    # ------------------------------------------------------------------ gate

    def _gate_pass(self, st, phone=None, result=None):
        """
        Two-sided "is this a real ad -> content return?" check, using only the cached labels.

        DESTINATION: the uprise marks the new, now-stable segment, so the most recent
        `probe_after` frames are what the viewer is looking at now. Suppress when those are
        (confidently, by majority) a blocked label — i.e. we rose into an ad, not content.

        PREVIOUS (when `prev_window > 0`): the `prev_window` frames just before the uprise
        (skipping `prev_gap` frames at the cut). Suppress when that window was confidently
        content (NOT a blocked label), because a real "break finished" alert must come OUT of
        an ad — a content -> content uprise is just a scene change inside the show. Reusing
        _majority with the inverse predicate fails open automatically: with no confident
        frames it returns False, so an uncertain previous window still alerts.
        """
        g = self._gate_cfg
        labels = list(st.labels)
        recent = labels[-g.probe_after:] if g.probe_after > 0 else labels

        blocked = self._majority(recent, lambda name: name in self._blocked)
        ok = not blocked

        prev_was_content = False
        previous = []
        if ok and g.prev_window > 0:
            end = len(labels) - (g.probe_after + g.prev_gap)  # exclusive upper bound
            previous = labels[max(0, end - g.prev_window):end] if end > 0 else []
            prev_was_content = self._majority(previous, lambda name: name not in self._blocked)
            if prev_was_content:
                ok = False

        # Record the attribution for this boundary (read by offline tools; see _PhoneState).
        st.last_gate = {"blocked": blocked, "prev_was_content": prev_was_content}

        if self.debug.enabled:
            t = getattr(result, "frame_index", "?")
            r = getattr(result, "ratio", float("nan"))
            self._log(f"[{phone}] BOUNDARY @t={t} ratio={r:.3f} | gate "
                      f"blocked={blocked} prev_was_content={prev_was_content} "
                      f"-> {'ALERT' if ok else 'SUPPRESSED'}")
            self._log(f"[{phone}]   recent={recent}")
            if g.prev_window > 0:
                self._log(f"[{phone}]   previous={previous}")
        return ok

    def _majority(self, labels, class_predicate):
        """
        True iff a strict majority of the *confident* frames in `labels` satisfy
        `class_predicate(class_name)`. With no confident frames, returns False — so an
        unsure segment is treated as "not blocked" and the uprise is allowed through.
        """
        thr = self._gate_cfg.confidence_threshold
        confident = [(name, cert) for (name, cert) in labels if cert >= thr]
        if not confident:
            return False
        hits = sum(1 for (name, _) in confident if class_predicate(name))
        return hits * 2 > len(confident)

    # ------------------------------------------------------------------ debug / session

    def _log(self, msg):
        print(f"[clip-debug] {msg}", flush=True)

    def _debug_periodic(self, phone, st, result):
        """Periodic visibility into the CLIP similarity signal (every log_every frames)."""
        n = self.debug.log_every or 1
        d = st.detector

        if result is None:
            # Still warming up: report buffer fill so "no alerts" is explainable.
            if d.t % n == 0:
                self._log(f"[{phone}] warming up {len(d.buffer)}/{d.buffer_size} "
                          f"(scoring starts at full buffer)")
            return

        if result.frame_index % n == 0:
            baseline_n = len(d._baseline)
            ready = baseline_n >= d.reference_window // 2
            self._log(
                f"[{phone}] t={result.frame_index} score={result.score:.4f} "
                f"smoothed={result.smoothed_score:.4f} ratio={result.ratio:.3f} "
                f"(trigger>={d.min_ratio}) baseline={baseline_n}/{d.reference_window} "
                f"ready={ready} boundaries={len(d.boundaries)}"
            )

    def end_session(self, phone_number):
        """
        Called when the client stops capturing. Saves the diagnostic plot (if debug is on)
        and clears this phone's streaming state so a fresh session starts clean.
        Returns the saved PNG path, or None.
        """
        with self._lock:
            st = self._phones.pop(phone_number, None)

        if st is None:
            if self.debug.enabled:
                self._log(f"[{phone_number}] end_session: no active state")
            return None

        if self.debug.enabled and self.debug.save_plot_on_stop:
            with st.lock:
                return self._save_plot(phone_number, st)
        return None

    def _save_plot(self, phone, st):
        d = st.detector
        if not getattr(d, "history_frames", None):
            self._log(f"[{phone}] end_session: no frames scored yet — nothing to plot")
            return None

        out_dir = os.path.abspath(self.debug.plot_dir)
        os.makedirs(out_dir, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9]+", "_", phone).strip("_") or "session"
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(out_dir, f"clip_{safe}_{ts}.png")
        title = f"adetector CLIP similarity — {phone} ({len(d.boundaries)} uprises)"

        try:
            saved = d.save_plot(path, title=title)
        except Exception as exc:  # never let plotting break the request
            self._log(f"[{phone}] end_session: failed to save plot ({exc})")
            return None

        if saved:
            self._log(f"[{phone}] saved CLIP plot -> {saved} "
                      f"({len(d.history_frames)} frames, {len(d.boundaries)} uprises)")
        return saved

    # ------------------------------------------------------------------ state mgmt

    def _get_state(self, phone_number):
        with self._lock:
            st = self._phones.get(phone_number)
            if st is None:
                detector = StreamingContextDetector(
                    self.clip_model,
                    self.clip_processor,
                    device=self.device,
                    **self.cfg.clip.detector_kwargs(),
                )
                # The label buffer must retain enough history for both gate windows: the
                # destination window (probe_after) and the previous window (prev_gap +
                # prev_window). Falls back to the detector's window when those are smaller.
                g = self._gate_cfg
                need = (g.probe_after + g.prev_gap + g.prev_window) if g else 0
                label_maxlen = (
                    max(self.cfg.clip.past_window_size + 1, need) if self.use_gate else 0
                )
                st = _PhoneState(detector, label_maxlen)
                self._phones[phone_number] = st
            return st

    def _evict_idle(self):
        ttl = self.cfg.state.idle_evict_minutes * 60.0
        if ttl <= 0:
            return
        now = time.time()
        with self._lock:
            stale = [p for p, s in self._phones.items() if now - s.last_seen > ttl]
            for p in stale:
                del self._phones[p]
