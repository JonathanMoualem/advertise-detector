"""
CLIP zero-shot classifier for the CLIP gate.

This is the streaming counterpart of the standalone classify.py PoC: each frame is
matched against a fixed set of textual descriptions via CLIP's native image<->text
matching (logits_per_image -> softmax over the labels), and the best-scoring
description wins. It exposes the contract AdBreakMonitor's gate expects:

    classify(img) -> (label, certainty)

so the gate's majority-vote suppression logic only sees free-text CLIP descriptions
turned into (label, certainty) pairs.

The CLIP model + processor are SHARED with the streaming context detector (passed in by
the monitor), so enabling the CLIP gate loads no additional model. The text features are
identical every frame, but we run the full forward per frame to stay faithful to the
PoC's math (logits_per_image already applies CLIP's logit scale before the softmax).
"""

import torch


class ClipGateClassifier:
    """Zero-shot CLIP classifier exposing the gate's classify(img) -> (label, certainty) contract."""

    def __init__(self, model, processor, labels, device="cpu"):
        if not labels:
            raise ValueError("ClipGateClassifier requires at least one label/description.")
        self.model = model
        self.processor = processor
        self.labels = list(labels)
        self.device = device

    def classify(self, img):
        """
        Zero-shot classify one PIL RGB frame against the configured descriptions.

        Mirrors classify.py's per-image inference: CLIP's full forward gives
        logits_per_image, softmax over the labels turns them into probabilities, and the
        argmax label + its probability are returned — the (label, certainty) contract the
        gate consumes.
        """
        with torch.no_grad():
            inputs = self.processor(
                text=self.labels,
                images=[img],
                return_tensors="pt",
                padding=True,
            ).to(self.device)
            probs = self.model(**inputs).logits_per_image.softmax(dim=1)  # [1, n_labels]
            top_prob, top_idx = probs.max(dim=1)
        return self.labels[int(top_idx.item())], float(top_prob.item())
