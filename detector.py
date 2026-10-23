"""Person detection backends.

YOLO (ultralytics) is used when installed: it is far more accurate and also
finds people who are sitting, partly hidden or far away. If it is not
installed, OpenCV's built-in HOG pedestrian detector is used instead, which
needs no download but only works well for standing people.
"""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class YoloPeopleDetector:
    name = "YOLO"

    def __init__(self, model_path: str = "yolov8n.pt"):
        from ultralytics import YOLO  # imported lazily so HOG works without it

        self.model = YOLO(model_path)  # downloads the weights on first use

    def detect(self, frame: np.ndarray, min_confidence: float) -> list[Detection]:
        # Class 0 in the COCO dataset is "person".
        result = self.model(frame, classes=[0], conf=min_confidence, verbose=False)[0]
        detections = []
        for box, conf in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
            x1, y1, x2, y2 = map(int, box)
            detections.append(Detection(x1, y1, x2, y2, float(conf)))
        return detections


class HogPeopleDetector:
    name = "HOG"

    def __init__(self):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame: np.ndarray, min_confidence: float) -> list[Detection]:
        # HOG is slow on big frames, so work on a copy at most 640 px wide.
        scale = min(1.0, 640 / frame.shape[1])
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
        rects, weights = self.hog.detectMultiScale(
            small, winStride=(8, 8), padding=(8, 8), scale=1.05
        )
        if len(rects) == 0:
            return []
        # HOG scores are roughly 0..2+; squash them into 0..1 so the GUI's
        # confidence slider means the same thing for both backends.
        scores = [float(1 - np.exp(-w)) for w in np.ravel(weights)]
        boxes = [[int(v / scale) for v in r] for r in rects]
        keep = cv2.dnn.NMSBoxes(boxes, scores, min_confidence, 0.4)
        detections = []
        for i in np.ravel(keep):
            x, y, w, h = boxes[i]
            detections.append(Detection(x, y, x + w, y + h, scores[i]))
        return detections


def create_detector(preferred: str = "auto"):
    """Return a detector. preferred is "auto", "yolo" or "hog"."""
    if preferred in ("auto", "yolo"):
        try:
            return YoloPeopleDetector()
        except ImportError:
            if preferred == "yolo":
                raise
    return HogPeopleDetector()


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    for n, d in enumerate(detections, start=1):
        cv2.rectangle(frame, (d.x1, d.y1), (d.x2, d.y2), (0, 200, 0), 2)
        label = f"#{n} {d.confidence:.0%}"
        cv2.putText(frame, label, (d.x1, max(15, d.y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 2)
    return frame
