import streamlit as st
import cv2
import numpy as np
import yt_dlp
import os
import tempfile
from pathlib import Path
from ultralytics import YOLO
import time
import matplotlib.pyplot as plt
from collections import deque

# ✅ PRIMEIRA CHAMADA STREAMLIT — OBRIGATÓRIO
st.set_page_config(page_title="Rastreamento de Veículos", layout="wide")

# =============== CSS PERSONALIZADO ===============
st.markdown("""
<style>
    .main { background-color: #f5f7fa; }
    .video-container {
        background: white;
        border-radius: 12px;
        padding: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .graph-container {
        background: white;
        border-radius: 12px;
        padding: 15px;
        margin-top: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .status-box {
        background: #e6f4ea;
        border-left: 4px solid #34a853;
        padding: 12px;
        border-radius: 0 8px 8px 0;
        margin: 15px 0;
    }
    .stButton>button {
        background-color: #1a73e8;
        color: white;
        border-radius: 8px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# =============== CONTADOR POR ID ÚNICO ===============
class UniqueVehicleCounter:
    def __init__(self):
        self.seen_ids = set()
        self.timeline = []  # [(timestamp, count)]

    def add_new_ids(self, current_ids):
        new_ids = [vid for vid in current_ids if vid not in self.seen_ids]
        for vid in new_ids:
            self.seen_ids.add(vid)
        if new_ids:
            self.timeline.append((time.time(), len(new_ids)))
        return len(new_ids), len(self.seen_ids)

    def get_cumulative_data(self):
        if not self.timeline:
            return [], []
        times = [t for t, c in self.timeline]
        counts = np.cumsum([c for t, c in self.timeline])
        return times, counts

# =============== FUNÇÕES ===============
@st.cache_resource
def load_model():
    return YOLO("yolov8n.pt")

def download_youtube_video(url, output_path):
    ydl_opts = {'format': 'best[height<=720][ext=mp4]', 'outtmpl': output_path, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# =============== TÍTULO ===============
st.title("🚨 Rastreamento Simples de Veículos")
st.markdown("Detecta **qualquer veículo** e conta por **ID único** (não por frame).")

# =============== SIDEBAR ===============
st.sidebar.header("📥 Fonte do Vídeo")
source_type = st.sidebar.radio("Escolha a fonte:", ("Upload de Vídeo", "Link do YouTube"))

video_path = None

if source_type == "Upload de Vídeo":
    uploaded_file = st.sidebar.file_uploader("Selecione um vídeo", type=["mp4", "avi", "mov", "mpeg4"])
    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
            tmp.write(uploaded_file.read())
            video_path = tmp.name
else:
    youtube_url = st.sidebar.text_input("Cole o link do YouTube")
    if st.sidebar.button("🔽 Baixar e Processar"):
        if youtube_url.strip():
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                try:
                    download_youtube_video(youtube_url, tmp.name)
                    video_path = tmp.name
                    st.sidebar.success("✅ Vídeo baixado com sucesso!")
                except Exception as e:
                    st.sidebar.error(f"❌ Erro ao baixar: {e}")
        else:
            st.sidebar.warning("Por favor, insira um link válido.")

frame_skip = st.sidebar.slider("⏩ Pular frames (para mais FPS)", 0, 10, 2)

# =============== LAYOUT ===============
col1, col2 = st.columns([2, 1])
video_placeholder = col1.empty()
graph_placeholder = col2.empty()
status_placeholder = st.empty()

# =============== PROCESSAMENTO ===============
if video_path and os.path.exists(video_path):
    cap = cv2.VideoCapture(video_path)
    model = load_model()
    counter = UniqueVehicleCounter()
    last_graph_update = time.time()

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            if frame_skip > 0 and current_frame % (frame_skip + 1) != 0:
                continue

            # Detectar veículos com tracking
            results = model.track(frame, classes=[2, 3, 5, 7], persist=True, verbose=False)
            current_ids = set()

            if results[0].boxes.id is not None:
                boxes = results[0].boxes
                for box, obj_id in zip(boxes.xyxy, boxes.id):
                    x1, y1, x2, y2 = map(int, box)
                    track_id = int(obj_id)
                    current_ids.add(track_id)
                    # Desenha bounding box e ID
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"ID {track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            new_count, total_unique = counter.add_new_ids(current_ids)

            # Mostrar vídeo
            video_placeholder.image(frame, channels="BGR")

            # Atualizar gráfico a cada 5s
            if time.time() - last_graph_update > 5:
                times, counts = counter.get_cumulative_data()
                if times:
                    fig, ax = plt.subplots(figsize=(5, 3.5))
                    ax.plot(times, counts, color='#1a73e8', marker='o', linewidth=2, markersize=4)
                    ax.set_title("Veículos Únicos Detectados (Acumulado)", fontsize=10)
                    ax.set_xlabel("Tempo (s)", fontsize=9)
                    ax.set_ylabel("Total", fontsize=9)
                    ax.grid(True, linestyle='--', alpha=0.6)
                    graph_placeholder.markdown('<div class="graph-container">', unsafe_allow_html=True)
                    graph_placeholder.pyplot(fig)
                last_graph_update = time.time()

            # Atualizar status
            status_placeholder.markdown(f"""
            <div class="status-box">
                <b>Veículos únicos detectados:</b> {total_unique}<br>
                <b>Novos neste ciclo:</b> {new_count}
            </div>
            """, unsafe_allow_html=True)

        cap.release()
        st.success("✅ Processamento concluído!")

    except Exception as e:
        st.error(f"Erro durante o processamento: {e}")

else:
    st.info("👉 Faça upload de um vídeo ou insira um link do YouTube para começar.")