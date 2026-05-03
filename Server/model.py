from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models


def _pick_torch_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    backend = getattr(torch.backends, "mps", None)
    if backend is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


MODELS_PATH = str(Path(__file__).resolve().parent / "model2.pth")
CLASSES_LIST = [
    "Soccer-Regular-Game", "Soccer-Recap", "Soccer-Highlight",
    "Studio", "Graphic", "Commercial",
    "Basketball-Regular-Game", "Basketball-Recap", "Basketball-Highlight", "Basketball-Pregame"
]
CLASSES = {cls: torch.tensor([i]) for i, cls in enumerate(CLASSES_LIST)}


class Model:

    def __init__(self):

        self.device = _pick_torch_device()
        print(self.device)

        self.model = models.efficientnet_b0(weights=None)
        num_ftrs = self.model.classifier[1].in_features
        self.model.classifier[1] = nn.Linear(num_ftrs, 10)

        checkpoint = torch.load(MODELS_PATH, map_location=self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(self.device)

        classes = checkpoint['class_mapping']
        self.model.eval()

        print("Model and Class Mapping loaded successfully!")

    def preprocess(self, img):
        img = img.resize((224, 224))
        vector = np.array(img, dtype=np.float32) / 255.0
        return torch.as_tensor(vector).permute(2, 0, 1).to(self.device)

    def output(self, img):
        img = self.preprocess(img)
        logits = self.model(img.unsqueeze(0))
        probs = F.softmax(logits, dim=1)

        # Get the top prediction
        max_prob, class_idx = torch.max(probs, dim=1)
        certainty = max_prob.item()
        idx = int(class_idx.item())

        return CLASSES_LIST[idx], certainty


class ContentMonitor:
    def __init__(self, streak_threshold=7, confidence_threshold=0.5):
        self.streak_threshold = streak_threshold
        self.confidence_threshold = confidence_threshold

        # Persistent State Variables - Initialized to non-content
        self.current_state = False
        self.current_streak_type = False

        self.streak_counter = 0  # How many consecutive confident frames?

    def process_frame_output(self, class_name, certainty):
        """
        Returns (state_changed, is_content): whether an alert-worthy transition fired,
        and whether the monitored streak type is "content" (game) vs non-content.
        Low-confidence frames do not advance streaks but always return (False, False).
        """
        is_content = "Basketball" in class_name or "Soccer" in class_name

        # 1. Ignore "noise" entirely (simulates the dataframe filtering)
        if certainty < self.confidence_threshold:
            return False, False

        # 2. Manage the streak
        if is_content == self.current_streak_type:
            # Continue the current streak
            self.streak_counter += 1
        else:
            # The streak broke! Start building a new streak of the opposite type
            self.current_streak_type = is_content
            self.streak_counter = 1

        # 3. Check for state transition
        if self.streak_counter == self.streak_threshold:
            # Only trigger if the new streak actually changes our overall state
            if self.current_streak_type != self.current_state:
                self.current_state = self.current_streak_type

                # Trigger the alert
                state_name = "Content" if self.current_state else "Non-Content"
                print(f"ALERT: Switched TO {state_name}")
                return True, self.current_state

        return False, False
