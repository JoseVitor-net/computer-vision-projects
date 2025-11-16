# object_tracking/tracker.py
import cv2
import numpy as np
from ultralytics import YOLO

class EuclideanDistTracker:
    def __init__(self, max_distance=50, disappear_threshold=10):
        self.next_id = 0
        self.tracks = {}  # id: {'centroid': (x, y), 'last_seen': frame_count}
        self.max_distance = max_distance
        self.disappear_threshold = disappear_threshold

    def update(self, detections, frame_count):
        centroids = []
        for x1, y1, x2, y2 in detections:
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            centroids.append((cx, cy))

        assigned = set()
        used_tracks = set()

        # Associar detecções aos tracks existentes (menor distância)
        for track_id, track in list(self.tracks.items()):
            min_dist = float('inf')
            best_idx = -1
            for i, (cx, cy) in enumerate(centroids):
                if i in assigned:
                    continue
                dist = np.linalg.norm(np.array(track['centroid']) - np.array([cx, cy]))
                if dist < min_dist and dist <= self.max_distance:
                    min_dist = dist
                    best_idx = i
            if best_idx != -1:
                assigned.add(best_idx)
                used_tracks.add(track_id)
                self.tracks[track_id] = {
                    'centroid': centroids[best_idx],
                    'last_seen': frame_count
                }

        # Criar novos tracks para detecções não associadas
        for i, centroid in enumerate(centroids):
            if i not in assigned:
                self.tracks[self.next_id] = {
                    'centroid': centroid,
                    'last_seen': frame_count
                }
                self.next_id += 1

        # Remover tracks antigos
        for track_id in list(self.tracks.keys()):
            if frame_count - self.tracks[track_id]['last_seen'] > self.disappear_threshold:
                del self.tracks[track_id]

        # Retornar [(cx, cy, id), ...]
        output = []
        for track_id, track in self.tracks.items():
            cx, cy = track['centroid']
            output.append((cx, cy, track_id))
        return output

    def get_active_count(self):
        return len(self.tracks)