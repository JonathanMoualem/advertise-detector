from pathlib import Path

import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models

import cv2
import itertools

from collections import deque


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


class VisualProcessor:

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

    def extract_color_fingerprint(self, img):
        """Expects 'img' to be a PIL Image."""
        # 1. Convert the PIL Image directly into a NumPy array
        cv_image = np.array(img)

        # 2. Convert from RGB (PIL's default) directly to HSV
        # Note: We changed cv2.COLOR_BGR2HSV to cv2.COLOR_RGB2HSV
        hsv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2HSV)

        # 3. Calculate and normalize the 3D histogram
        hist = cv2.calcHist([hsv_image], [0, 1, 2], None, [50, 60, 60], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        return hist

    def output(self, img):
        color_fp = self.extract_color_fingerprint(img)
        img = self.preprocess(img)
        logits = self.model(img.unsqueeze(0))
        probs = F.softmax(logits, dim=1)

        # Get the top prediction
        max_prob, class_idx = torch.max(probs, dim=1)
        certainty = max_prob.item()
        idx = int(class_idx.item())

        return CLASSES_LIST[idx], certainty, color_fp


class ContentMonitor:
    def __init__(self, streak_threshold=7, confidence_threshold=0.5, color_histogram_threshold=0.4):
        self.streak_threshold = streak_threshold
        self.confidence_threshold = confidence_threshold
        self.color_histogram_threshold = color_histogram_threshold
        self.color_histogram_group = deque(maxlen=streak_threshold)

        # Persistent State Variables - Initialized to non-content
        self.current_state = False
        self.current_streak_type = False

        self.streak_counter = 0  # How many consecutive confident frames?

    def calculate_color_distance(self, hist1, hist2):
        return cv2.compareHist(hist1, hist2, cv2.HISTCMP_BHATTACHARYYA)

    def analyze_group_cohesion(self):

        # Generate all unique pairs directly from the deque
        unique_pairs = list(itertools.combinations(self.color_histogram_group, 2))

        # Calculate the distance for every pair
        all_distances = [self.calculate_color_distance(h1, h2) for h1, h2 in unique_pairs]

        # Return the average distance
        return np.mean(all_distances)

    def process_frame_output(self, class_name, certainty, color_fp):
        """
        Returns (state_changed, is_content): whether an alert-worthy transition fired,
        and whether the monitored streak type is "content" (game) vs non-content.
        Low-confidence frames do not advance streaks but always return (False, False).
        """
        self.color_histogram_group.append(color_fp)

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

            # If current state is content, adjust to group color fingerprint cohesion
            if self.current_state:
                group_cohesion = self.analyze_group_cohesion()
                if group_cohesion >= self.color_histogram_threshold:
                    self.streak_counter = 0  # We assume we are still in an ad break so we reset the streak counter
                    return False, False

            # Only trigger if the new streak actually changes our overall state
            if self.current_streak_type != self.current_state:
                self.current_state = self.current_streak_type

                # Trigger the alert
                state_name = "Content" if self.current_state else "Non-Content"
                print(f"ALERT: Switched TO {state_name}")
                return True, self.current_state

        return False, False
