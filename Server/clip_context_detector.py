import os
import sys
from collections import deque
from dataclasses import dataclass

import torch
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from transformers import CLIPProcessor, CLIPModel


def _pick_torch_device():
    """Best available torch device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    backend = getattr(torch.backends, "mps", None)
    if backend is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def setup_clip_model(model_id="openai/clip-vit-base-patch32", device="mps"):
    """
    Initializes and returns the CLIP model and processor.
    """
    print(f"Loading CLIP model '{model_id}' on {device}...")
    processor = CLIPProcessor.from_pretrained(model_id)
    model = CLIPModel.from_pretrained(model_id).to(device)
    model.eval()
    return model, processor


def _as_embedding_tensor(features):
    """
    Hugging Face sometimes returns a dataclass instead of a raw tensor.
    This pulls out the actual embedding tensor.
    """
    if isinstance(features, torch.Tensor):
        return features
    if hasattr(features, "image_embeds"):
        return features.image_embeds
    if hasattr(features, "pooler_output"):
        return features.pooler_output
    raise ValueError("Could not find the embedding tensor in the model output.")


def extract_features(image_list, model, processor, device, batch_size=32):
    """
    Passes a LIST of images through CLIP and returns normalized feature vectors.
    Kept for offline / batch use; the streaming path uses embed_frame() instead.
    """
    print("Extracting CLIP features...")
    all_embeddings = []

    with torch.no_grad():
        for i in range(0, len(image_list), batch_size):
            batch_imgs = image_list[i : i + batch_size]
            inputs = processor(images=batch_imgs, return_tensors="pt").to(device)
            features = _as_embedding_tensor(model.get_image_features(**inputs))
            features = features / features.norm(p=2, dim=-1, keepdim=True)
            all_embeddings.append(features.cpu())

    return torch.cat(all_embeddings, dim=0)


def embed_frame(frame, model, processor, device):
    """
    Embeds a SINGLE frame and returns its L2-normalized feature vector of shape [D].
    This is the per-frame entry point used by the streaming detector.
    """
    with torch.no_grad():
        inputs = processor(images=[frame], return_tensors="pt").to(device)
        features = _as_embedding_tensor(model.get_image_features(**inputs))
        features = features / features.norm(p=2, dim=-1, keepdim=True)
    return features.squeeze(0).cpu()


@dataclass
class FrameResult:
    """Result emitted once per scored frame (the current frame -- zero look-ahead)."""
    frame_index: int       # the frame just scored & (if flagged) alerted on -- no look-ahead delay
    score: float           # raw similarity of the current frame to the trailing past window
    smoothed_score: float  # causal (trailing) smoothed score, for the plot
    ratio: float           # cur / trailing-baseline-median -- the RELATIVE jump (content-agnostic)
    is_boundary: bool      # True if a MAJOR uprise (transition) was flagged at this frame


class StreamingContextDetector:
    """
    Online context-break detector for a broadcast stream.

    You feed it ONE frame at a time via process_frame(). It keeps a rolling buffer of
    recent frame embeddings and, the moment frame `t` arrives, scores `t` itself:

        score(t) = mean cosine similarity of the CURRENT frame to the trailing
                   `past_window_size` frames

    There is NO look-ahead: the decision frame is the current frame, so an alert fires
    with zero latency. A rise in this score means the current frame suddenly matches the
    recent past much better -- i.e. the stream has entered a stable / repetitive segment.

    The decision is deliberately STRICT and content-agnostic. Instead of an absolute
    threshold, it triggers on RELATIVE change: it flags when the de-noised score is at
    least `min_ratio` times a robust (median) trailing baseline -- e.g. min_ratio=1.28
    means "the current similarity jumped to ~1.28x the recent norm". Because it is a
    ratio, the same setting works whether a given broadcast's baseline similarity is
    high or low. Raise min_ratio to be stricter, lower it to be more sensitive.
    """

    def __init__(
        self,
        model,
        processor,
        device="cpu",
        past_window_size=29,         # how many past frames the current frame is compared against
        visual_smooth_window=21,     # PLOT-ONLY trailing window for the smoothed line (no decision effect)
        min_ratio=1.28,              # STRICT gate: flag when cur >= min_ratio * reference-window median
        reference_window=120,        # trailing window of raw scores -> median baseline (also gates warm-up)
        trigger_denoise_window=3,    # short trailing avg of the score used in the decision (noise robustness)
        cooldown=60,                 # min frames between two transition flags
    ):
        self.model = model
        self.processor = processor
        self.device = device

        self.past_window_size = past_window_size
        self.visual_smooth_window = visual_smooth_window
        self.min_ratio = min_ratio
        self.reference_window = reference_window
        self.cooldown = cooldown

        # No look-ahead: buffer holds the past window + the current frame.
        self.buffer_size = past_window_size + 1
        self.buffer = deque(maxlen=self.buffer_size)

        self.t = -1  # global index of the most recently received frame

        # Causal state.
        self._plot_smooth = deque(maxlen=visual_smooth_window)       # plotted smoothed line (visual only)
        self._trigger_denoise = deque(maxlen=trigger_denoise_window)  # light de-noise for the decision
        self._baseline = deque(maxlen=reference_window)              # trailing raw scores -> median baseline
        self._last_boundary = -(10 ** 9)

        # History for the final graph.
        self.history_frames = []
        self.history_raw = []
        self.history_smoothed = []
        self.boundaries = []

    def process_frame(self, frame):
        """
        Ingest a single frame and score it immediately (zero look-ahead). Returns a
        FrameResult for the current frame, or None while the buffer is still warming up.
        """
        self.buffer.append(embed_frame(frame, self.model, self.processor, self.device))
        self.t += 1

        # Warming up: not enough frames yet to form the past window + current frame.
        if len(self.buffer) < self.buffer_size:
            return None

        embs = torch.stack(list(self.buffer))         # [past_window_size + 1, D]
        past_window = embs[: self.past_window_size]    # the trailing past frames
        current = embs[self.past_window_size:]         # the current frame, shape [1, D]

        # Similarity of the CURRENT frame to the recent past (no future involved).
        score = torch.matmul(past_window, current.T).mean().item()

        decision_index = self.t  # we score the current frame itself -> no latency

        # --- Causal smoothing for the plotted line (visualization only) ---
        self._plot_smooth.append(score)
        smoothed = sum(self._plot_smooth) / len(self._plot_smooth)

        # --- De-noised decision signal ---
        self._trigger_denoise.append(score)
        cur = sum(self._trigger_denoise) / len(self._trigger_denoise)

        # --- Strict RELATIVE decision (causal: uses only past scores) ---
        # Flag a MAJOR uprise when the de-noised similarity has jumped to at least
        # min_ratio times its robust (median) trailing baseline. A ratio (rather than an
        # absolute rise) keeps the trigger meaningful across content with different
        # baseline similarity levels.
        is_boundary = False
        ratio = 1.0
        if len(self._baseline) >= self.reference_window // 2:
            median = float(np.median(np.fromiter(self._baseline, dtype=float)))
            if median > 0:
                ratio = cur / median
            if ratio >= self.min_ratio and (decision_index - self._last_boundary) > self.cooldown:
                is_boundary = True
                self._last_boundary = decision_index
                self.boundaries.append(decision_index)
        # Append AFTER deciding so a point never biases its own baseline.
        self._baseline.append(score)

        self.history_frames.append(decision_index)
        self.history_raw.append(score)
        self.history_smoothed.append(smoothed)

        return FrameResult(decision_index, score, smoothed, ratio, is_boundary)

    def plot(self, title=None):
        """
        Reproduces the original diagnostic graph (raw + smoothed similarity),
        with vertical markers at the detected uprise transitions.
        """
        plt.figure(figsize=(15, 5))
        plt.plot(self.history_frames, self.history_raw,
                 label="Raw Signal", color="lightblue", alpha=0.6)
        plt.plot(self.history_frames, self.history_smoothed,
                 label="Smoothed Signal (causal)", color="mediumblue", linewidth=2)

        for j, b in enumerate(self.boundaries):
            plt.axvline(b, color="red", linestyle="--", alpha=0.7,
                        label="Detected Uprise" if j == 0 else None)

        plt.title(title or f"Streaming Broadcast Segmentation "
                           f"(Causal, no look-ahead | min_ratio={self.min_ratio})")
        plt.xlabel("Frame Index")
        plt.ylabel("Cosine Similarity")
        plt.legend(loc="lower right")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    def save_plot(self, path, title=None):
        """
        Same diagnostic graph as plot(), but rendered to a PNG file instead of shown.
        Headless-safe (no display needed). Returns the path written, or None if there is
        nothing to plot yet.
        """
        if not self.history_frames:
            return None

        fig = plt.figure(figsize=(15, 5))
        plt.plot(self.history_frames, self.history_raw,
                 label="Raw Signal", color="lightblue", alpha=0.6)
        plt.plot(self.history_frames, self.history_smoothed,
                 label="Smoothed Signal (causal)", color="mediumblue", linewidth=2)

        for j, b in enumerate(self.boundaries):
            plt.axvline(b, color="red", linestyle="--", alpha=0.7,
                        label="Detected Uprise" if j == 0 else None)

        plt.title(title or f"Streaming Broadcast Segmentation "
                           f"(Causal, no look-ahead | min_ratio={self.min_ratio})")
        plt.xlabel("Frame Index")
        plt.ylabel("Cosine Similarity")
        plt.legend(loc="lower right")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return path


def iter_image_frames(directory):
    """
    Yields frames from a folder of image files ONE AT A TIME (as PIL RGB images),
    sorted by filename, simulating a live stream. This matches the PoC's test-data
    layout. Swap this out for any source that hands you frames individually.
    """
    directory = os.path.expanduser(directory)
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    names = sorted(n for n in os.listdir(directory) if n.lower().endswith(exts))
    for name in names[::2]:
        yield name, Image.open(os.path.join(directory, name)).convert("RGB")


if __name__ == "__main__":
    # Frame source: a folder of images (default ./test-data), overridable via argv.
    source_dir = sys.argv[1] if len(sys.argv) > 1 else "./test-data"

    device = _pick_torch_device()
    model, processor = setup_clip_model(device=device)
    detector = StreamingContextDetector(model, processor, device=device)

    # Frames arrive ONE AT A TIME, just like a live stream would deliver them.
    # Keep the filenames in arrival order so a flagged transition can be reported by
    # name for visual verification. With no look-ahead, the alert fires on this frame.
    names = []
    for name, frame in iter_image_frames(source_dir):
        names.append(name)
        result = detector.process_frame(frame)
        if result is not None and result.is_boundary:
            print(f"Transition (uprise) at frame {result.frame_index} "
                  f"[{names[result.frame_index]}] "
                  f"| ratio={result.ratio:.3f} (x baseline) score={result.score:.3f}")

    detector.plot()
