import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F

from torchvision import models


MODELS_PATH = './Server/model2.pth'
CLASSES_LIST = [
    "Soccer-Regular-Game", "Soccer-Recap", "Soccer-Highlight",
    "Studio", "Graphic", "Commercial",
    "Basketball-Regular-Game", "Basketball-Recap", "Basketball-Highlight", "Basketball-Pregame"
]
CLASSES = {cls: torch.tensor([i]) for i, cls in enumerate(CLASSES_LIST)}


class Model:

    def __init__(self):

        self.device = torch.device('mps' if torch.mps.is_available() else 'cpu')
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

        return CLASSES_LIST[class_idx], certainty


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
        Feed this function one frame at a time.
        It returns an alert string if a state change occurs, otherwise returns None.
        """
        is_content = "Basketball" in class_name or "Soccer" in class_name

        # 1. Ignore "noise" entirely (simulates the dataframe filtering)
        if certainty < self.confidence_threshold:
            return None

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

        # Return None if no alert was triggered on this frame
        return False, False
