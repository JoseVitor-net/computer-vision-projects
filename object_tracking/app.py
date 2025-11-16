# object_tracking/app.py
import streamlit as st
import cv2
import numpy as np
import yt_dlp
from ultralytics import YOLO
from .tracker import EuclideanDistTracker
from .reporter import TrafficReporter
import time

# Carregar modelo uma vez
@st.cache_resource
def load_model():
    return YOLO("yolov8n.pt")

def get_youtube_stream_url(youtube_url):
    ydl_opts = {
        'quiet': True,
        'format': 'best[height<=720]/best',
        'noplaylist': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return info['url']

st.set_page_config(page_title="Rastreamento de Veículos ao Vivo", layout="wide")
st.title("🚦 Rastreamento de Veículos em Lives do YouTube (YOLOv8 + Streamlit)")

# Sidebar
st.sidebar.header("Configurações")
youtube_url = st.sidebar.text_input("URL da Live do YouTube", value="")
frame_skip = st.sidebar.slider("Pular frames (para melhorar FPS)", 0, 10, 2)

if not youtube_url:
    st.info("Cole o link de uma live do YouTube (ex: câmera de rodovia) para começar.")
    st.stop()

try:
    stream_url = get_youtube_stream_url(youtube_url)
except Exception as e:
    st.error(f"Erro ao carregar live: {e}")
    st.stop()

# Inicializar componentes
model = load_model()
tracker = EuclideanDistTracker()
reporter = TrafficReporter()
cap = cv2.VideoCapture(stream_url)

# Containers para UI
video_placeholder = st.empty()
report_placeholder = st.sidebar.empty()
download_placeholder = st.sidebar.empty()

frame_count = 0
last_report_time = time.time()

try:
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            st.warning("Fim do stream ou erro na conexão.")
            break

        frame_count += 1
        if frame_skip > 0 and frame_count % (frame_skip + 1) != 0:
            continue

        # Detecção com YOLO (apenas carros, caminhões, ônibus)
        results = model(frame, classes=[2, 3, 5, 7], verbose=False)  # COCO: car=2, motorcycle=3, bus=5, truck=7
        detections = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append([x1, y1, x2, y2])

        # Rastreamento
        tracked_objects = tracker.update(detections, frame_count)
        vehicle_count = len(tracked_objects)

        # Atualizar relatório
        reporter.add_frame_detections(vehicle_count)

        # Desenhar bounding boxes e IDs
        for (cx, cy, obj_id) in tracked_objects:
            cv2.putText(frame, f"ID {obj_id}", (cx - 20, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

        # Mostrar frame
        video_placeholder.image(frame, channels="BGR", use_container_width=True)

        # Atualizar relatório a cada 5 segundos
        if time.time() - last_report_time > 5:
            report = reporter.get_report()
            report_placeholder.json(report)
            last_report_time = time.time()

        # Botão de download
        csv_file = reporter.export_to_csv()
        if csv_file:
            with open(csv_file, "rb") as f:
                download_placeholder.download_button("📥 Baixar Relatório CSV", f, file_name=csv_file, mime="text/csv")

finally:
    cap.release()