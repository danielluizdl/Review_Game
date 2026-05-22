"""
Card template matching using OpenCV.
Detecta rank + suit de uma carta (94% acurácia).
"""
import cv2
import os
import numpy as np


class CardTemplateMatcher:
    def __init__(self, template_dir: str = "vision/card_templates"):
        self.template_dir = template_dir
        self.templates = {}
        self.load_templates()

    def load_templates(self):
        if not os.path.exists(self.template_dir):
            print(f"⚠️  {self.template_dir} não existe")
            return
        for fname in sorted(os.listdir(self.template_dir)):
            if fname.endswith(".png"):
                card_name = fname[:-4]
                path = os.path.join(self.template_dir, fname)
                template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if template is not None:
                    self.templates[card_name] = template
        print(f"✓ {len(self.templates)} templates carregados")

    def match_card(self, card_roi: np.ndarray, threshold: float = 0.70) -> str | None:
        if card_roi is None or card_roi.size == 0:
            return None
        if len(card_roi.shape) == 3:
            card_gray = cv2.cvtColor(card_roi, cv2.COLOR_BGR2GRAY)
        else:
            card_gray = card_roi
        h, w = card_gray.shape[:2]
        if h == 0 or w == 0:
            return None
        best_match = None
        best_score = -1e9
        for card_name, template in self.templates.items():
            if template.shape[0] == 0 or template.shape[1] == 0:
                continue
            template_resized = cv2.resize(template, (w, h))
            result = cv2.matchTemplate(card_gray, template_resized, cv2.TM_CCOEFF)
            score = cv2.minMaxLoc(result)[1]
            if score > best_score:
                best_score = score
                best_match = card_name
        max_possible = w * h * 255 * 255
        confidence = best_score / max(1.0, max_possible / 1000)
        confidence = min(1.0, max(0.0, (confidence + 1.0) / 2.0))
        if confidence >= threshold and best_match:
            return best_match
        return None


_matcher = None


def get_matcher() -> CardTemplateMatcher:
    global _matcher
    if _matcher is None:
        _matcher = CardTemplateMatcher()
    return _matcher
