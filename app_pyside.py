# app_pyside.py
import sys
import cv2
import numpy as np
import yt_dlp
import os
import tempfile
import time
from pathlib import Path
from ultralytics import YOLO
from collections import deque

# Importa componentes do PySide6
from PySide6.QtCore import (
    QObject, QThread, Signal, Slot, Qt
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QRadioButton, QLineEdit, QSlider,
    QFileDialog, QGroupBox, QMessageBox,
    QSizePolicy  # <--- IMPORTANTE: Importar QSizePolicy
)
from PySide6.QtGui import QImage, QPixmap

# Importa componentes do Matplotlib para integração com Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

# =============== CONTADOR POR ID ÚNICO (Idêntico ao seu) ===============
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
        # Normaliza o tempo para começar em 0
        start_time = self.timeline[0][0]
        times = [t - start_time for t, c in self.timeline]
        counts = np.cumsum([c for t, c in self.timeline])
        return times, counts

# =============== FUNÇÕES (Idêntico ao seu) ===============
@Slot()
def load_model():
    return YOLO("yolov8n.pt")

def download_youtube_video(url, output_path):
    ydl_opts = {'format': 'best[height<=720][ext=mp4]', 'outtmpl': output_path, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# =============== WORKER DE VÍDEO (Lógica de Processamento) ===============
class VideoWorker(QObject):
    # Sinais (Signals) para enviar dados de volta para a GUI
    frame_ready = Signal(np.ndarray)      # Envia o frame (imagem)
    stats_updated = Signal(int, int)    # Envia (total_unico, novo_ciclo)
    graph_data_ready = Signal(object, object) # Envia (tempos, contagens)
    processing_finished = Signal()      # Avisa que terminou
    error_occurred = Signal(str)        # Envia uma mensagem de erro

    def __init__(self, video_path, source_type, youtube_url, frame_skip):
        super().__init__()
        self.video_path_input = video_path
        self.source_type = source_type
        self.youtube_url = youtube_url
        self.frame_skip = frame_skip
        self._is_running = True

    @Slot()
    def run(self):
        """Inicia o processamento do vídeo."""
        try:
            video_path = self.video_path_input
            
            if self.source_type == "YouTube" and self.youtube_url:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                    download_youtube_video(self.youtube_url, tmp.name)
                    video_path = tmp.name
            
            if not video_path or not os.path.exists(video_path):
                raise ValueError("Arquivo de vídeo não encontrado ou inválido.")

            model = load_model()
            cap = cv2.VideoCapture(video_path)
            counter = UniqueVehicleCounter()
            last_graph_update = time.time()

            while cap.isOpened() and self._is_running:
                ret, frame = cap.read()
                if not ret:
                    break

                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                if self.frame_skip > 0 and current_frame % (self.frame_skip + 1) != 0:
                    continue

                results = model.track(frame, classes=[2, 3, 5, 7], persist=True, verbose=False)
                current_ids = set()

                if results[0].boxes.id is not None:
                    boxes = results[0].boxes
                    for box, obj_id in zip(boxes.xyxy, boxes.id):
                        x1, y1, x2, y2 = map(int, box)
                        track_id = int(obj_id)
                        current_ids.add(track_id)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, f"ID {track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                new_count, total_unique = counter.add_new_ids(current_ids)

                self.frame_ready.emit(frame)
                self.stats_updated.emit(total_unique, new_count)

                if time.time() - last_graph_update > 5:
                    times, counts = counter.get_cumulative_data()
                    if len(times) > 0:
                        self.graph_data_ready.emit(times, counts)
                    last_graph_update = time.time()

            cap.release()

        except Exception as e:
            self.error_occurred.emit(f"Erro no processamento: {e}")
        finally:
            self.processing_finished.emit()

    def stop(self):
        self._is_running = False

# =============== JANELA PRINCIPAL (GUI) ===============
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rastreamento de Veículos (PySide6)")
        self.setGeometry(100, 100, 1200, 700)
        
        self.video_path = None
        self.worker_thread = None
        self.video_worker = None

        self.init_ui()
        self.apply_stylesheet()

    def init_ui(self):
        main_layout = QHBoxLayout()
        
        # --- 1. Sidebar (Esquerda) ---
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(15)
        
        self.title_label = QLabel("🚨 Rastreamento de Veículos")
        self.title_label.setObjectName("TitleLabel")
        sidebar_layout.addWidget(self.title_label)

        source_group = QGroupBox("📥 Fonte do Vídeo")
        source_layout = QVBoxLayout()
        self.radio_upload = QRadioButton("Upload de Vídeo")
        self.radio_youtube = QRadioButton("Link do YouTube")
        self.radio_upload.setChecked(True)
        source_layout.addWidget(self.radio_upload)
        source_layout.addWidget(self.radio_youtube)
        source_group.setLayout(source_layout)
        sidebar_layout.addWidget(source_group)

        self.btn_select_file = QPushButton("Selecione um vídeo")
        self.btn_select_file.clicked.connect(self.select_file)
        self.selected_file_label = QLabel("Nenhum arquivo selecionado.")
        self.selected_file_label.setWordWrap(True)
        sidebar_layout.addWidget(self.btn_select_file)
        sidebar_layout.addWidget(self.selected_file_label)

        self.youtube_input = QLineEdit()
        self.youtube_input.setPlaceholderText("Cole o link do YouTube")
        self.youtube_input.setEnabled(False) 
        sidebar_layout.addWidget(self.youtube_input)
        
        self.radio_upload.toggled.connect(self.toggle_source_controls)
        self.radio_youtube.toggled.connect(self.toggle_source_controls)

        sidebar_layout.addWidget(QLabel("⏩ Pular frames (para mais FPS)"))
        self.frame_skip_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_skip_slider.setRange(0, 10)
        self.frame_skip_slider.setValue(2)
        self.frame_skip_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        sidebar_layout.addWidget(self.frame_skip_slider)

        self.btn_process = QPushButton("🔽 Processar Vídeo")
        self.btn_process.setObjectName("ProcessButton")
        self.btn_process.clicked.connect(self.start_processing)
        sidebar_layout.addWidget(self.btn_process)
        
        sidebar_layout.addStretch() 

        sidebar_widget = QWidget()
        sidebar_widget.setLayout(sidebar_layout)
        sidebar_widget.setObjectName("Sidebar")
        
        # --- 2. Área de Conteúdo (Direita) ---
        content_layout = QVBoxLayout()
        top_content_layout = QHBoxLayout()
        
        # Coluna do Vídeo
        self.video_label = QLabel("Faça upload de um vídeo ou insira um link para começar.")
        
        # =================================================================
        # CORREÇÃO DEFINITIVA:
        # 1. Mantém o scale automático (correção anterior)
        self.video_label.setScaledContents(True)
        
        # 2. Força o QLabel a IGNORAR o tamanho do vídeo e obedecer o layout
        self.video_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        # =================================================================
        
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setObjectName("VideoContainer")
        top_content_layout.addWidget(self.video_label, 2) # Ocupa 2/3 do espaço

        # Coluna do Gráfico
        self.graph_container = QWidget()
        self.graph_container.setObjectName("GraphContainer")
        graph_layout = QVBoxLayout()
        
        self.fig, self.ax = plt.subplots(figsize=(5, 3.5))
        self.graph_canvas = FigureCanvasQTAgg(self.fig)
        graph_layout.addWidget(self.graph_canvas)
        self.graph_container.setLayout(graph_layout)
        
        top_content_layout.addWidget(self.graph_container, 1) # Ocupa 1/3 do espaço
        content_layout.addLayout(top_content_layout)
        
        # Status Box (Inferior)
        self.status_label = QLabel("<b>Status:</b> Aguardando...")
        self.status_label.setObjectName("StatusBox")
        self.status_label.setMargin(10)
        content_layout.addWidget(self.status_label)

        # --- Montagem Final ---
        main_layout.addWidget(sidebar_widget, 1) 
        main_layout.addLayout(content_layout, 3)   

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def apply_stylesheet(self):
        """Aplica o CSS personalizado."""
        self.setStyleSheet("""
            QWidget {
                font-family: Arial, sans-serif;
            }
            #Sidebar {
                background-color: #f5f7fa;
                border-right: 1px solid #ddd;
            }
            #TitleLabel {
                font-size: 20px;
                font-weight: bold;
                color: #333;
            }
            #VideoContainer {
                background: white;
                border-radius: 12px;
                padding: 10px;
                border: 1px solid #eee;
            }
            #GraphContainer {
                background: white;
                border-radius: 12px;
                padding: 10px;
                border: 1px solid #eee;
            }
            #StatusBox {
                background: #e6f4ea;
                border-left: 4px solid #34a853;
                border-radius: 8px;
                font-size: 14px;
            }
            #ProcessButton {
                background-color: #1a73e8;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }
            #ProcessButton:disabled {
                background-color: #999;
            }
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 8px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QGroupBox {
                font-weight: bold;
            }
        """)

    @Slot()
    def toggle_source_controls(self):
        if self.radio_upload.isChecked():
            self.btn_select_file.setEnabled(True)
            self.youtube_input.setEnabled(False)
        else: # YouTube
            self.btn_select_file.setEnabled(False)
            self.youtube_input.setEnabled(True)

    @Slot()
    def select_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Selecione um vídeo", "", 
            "Vídeos (*.mp4 *.avi *.mov *.mpeg4)"
        )
        if file_name:
            self.video_path = file_name
            self.selected_file_label.setText(f"Selecionado: {Path(file_name).name}")

    @Slot()
    def start_processing(self):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            QMessageBox.warning(self, "Aviso", "Processamento já em andamento.")
            return

        source_type = "Upload" if self.radio_upload.isChecked() else "YouTube"
        youtube_url = self.youtube_input.text().strip()
        frame_skip = self.frame_skip_slider.value()

        if source_type == "Upload" and not self.video_path:
            QMessageBox.critical(self, "Erro", "Selecione um arquivo de vídeo primeiro.")
            return
        if source_type == "YouTube" and not youtube_url:
            QMessageBox.critical(self, "Erro", "Insira um link do YouTube válido.")
            return

        self.btn_process.setText("Processando...")
        self.btn_process.setEnabled(False)
        self.status_label.setText("<b>Status:</b> Iniciando processamento...")

        self.worker_thread = QThread()
        self.video_worker = VideoWorker(
            video_path=self.video_path,
            source_type=source_type,
            youtube_url=youtube_url,
            frame_skip=frame_skip
        )
        self.video_worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.video_worker.run)
        self.video_worker.frame_ready.connect(self.update_video_frame)
        self.video_worker.stats_updated.connect(self.update_stats)
        self.video_worker.graph_data_ready.connect(self.update_graph)
        self.video_worker.processing_finished.connect(self.processing_finished)
        self.video_worker.error_occurred.connect(self.processing_error)

        self.worker_thread.start()

    @Slot(np.ndarray)
    def update_video_frame(self, frame):
        # Converte BGR (OpenCV) para RGB (Qt)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        
        q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        
        # Apenas seta o Pixmap. O scaling agora é 100% automático
        # graças às propriedades setadas no init_ui
        self.video_label.setPixmap(QPixmap.fromImage(q_image))

    @Slot(int, int)
    def update_stats(self, total_unique, new_count):
        self.status_label.setText(
            f"<b>Veículos únicos detectados:</b> {total_unique}<br>"
            f"<b>Novos neste ciclo:</b> {new_count}"
        )

    @Slot(object, object)
    def update_graph(self, times, counts):
        if len(times) > 0:
            self.ax.clear()
            self.ax.plot(times, counts, color='#1a73e8', marker='o', linewidth=2, markersize=4)
            self.ax.set_title("Veículos Únicos Detectados (Acumulado)", fontsize=10)
            self.ax.set_xlabel("Tempo (s)", fontsize=9)
            self.ax.set_ylabel("Total", fontsize=9)
            self.ax.grid(True, linestyle='--', alpha=0.6)
            self.fig.tight_layout()
            self.graph_canvas.draw() 

    @Slot()
    def processing_finished(self):
        self.status_label.setText("<b>Status:</b> Processamento concluído!")
        self.btn_process.setText("🔽 Processar Vídeo")
        self.btn_process.setEnabled(True)
        self.cleanup_thread()

    @Slot(str)
    def processing_error(self, error_message):
        QMessageBox.critical(self, "Erro no Processamento", error_message)
        self.status_label.setText(f"<b>Status:</b> Erro! {error_message}")
        self.btn_process.setText("🔽 Processar Vídeo")
        self.btn_process.setEnabled(True)
        self.cleanup_thread()
    
    def cleanup_thread(self):
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait()
        self.worker_thread = None
        self.video_worker = None

    def closeEvent(self, event):
        if self.video_worker:
            self.video_worker.stop()
        self.cleanup_thread()
        event.accept()

# =============== Ponto de Entrada ===============
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())