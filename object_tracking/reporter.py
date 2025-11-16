# object_tracking/reporter.py
from collections import deque
import time
import pandas as pd

class TrafficReporter:
    def __init__(self, interval_10=600, interval_30=1800, interval_60=3600):
        self.events = deque(maxlen=10000)  # evita consumo infinito de memória
        self.interval_10 = interval_10
        self.interval_30 = interval_30
        self.interval_60 = interval_60

    def add_frame_detections(self, count):
        self.events.append((time.time(), count))

    def get_report(self):
        if not self.events:
            return {"avg_10min": 0, "avg_30min": 0, "avg_60min": 0, "last_update": "N/A"}
        now = time.time()
        data_10 = [c for t, c in self.events if now - t <= self.interval_10]
        data_30 = [c for t, c in self.events if now - t <= self.interval_30]
        data_60 = [c for t, c in self.events if now - t <= self.interval_60]

        avg_10 = sum(data_10) / len(data_10) if data_10 else 0
        avg_30 = sum(data_30) / len(data_30) if data_30 else 0
        avg_60 = sum(data_60) / len(data_60) if data_60 else 0

        return {
            "avg_10min": round(avg_10, 2),
            "avg_30min": round(avg_30, 2),
            "avg_60min": round(avg_60, 2),
            "last_update": time.strftime("%H:%M:%S", time.localtime(now))
        }

    def export_to_csv(self, filename="traffic_report.csv"):
        if not self.events:
            return None
        df = pd.DataFrame(list(self.events), columns=["timestamp", "vehicle_count"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        df.to_csv(filename, index=False)
        return filename