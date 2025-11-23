# app_pyside_pyqtgraph_SIMPLIFICADO.py
# Sistema Profissional de Rastreamento de Veículos
# VERSÃO SIMPLIFICADA: Upload Local + YouTube Streaming Direto
# COM CORREÇÕES DO YOUTUBE JÁ APLICADAS

import sys
import cv2
import numpy as np
import yt_dlp
import os
import time
from pathlib import Path
from ultralytics import YOLO
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QRadioButton, QLineEdit, QSlider,
    QFileDialog, QGroupBox, QMessageBox, QSizePolicy, QFrame, QTabWidget
)
from PySide6.QtGui import QImage, QPixmap, QColor, QPalette
import pyqtgraph as pg

# ========== CONFIGURAÇÕES ==========
VEHICLE_CLASSES = {
    2: 'Carro',
    3: 'Moto',
    5: 'Ônibus',
    7: 'Caminhão'
}

SIMPLE_VEHICLE_MAP = {
    2: 'Carro',
    3: 'Moto',
    5: 'Caminhão',
    7: 'Caminhão'
}

VEHICLE_COLORS = {
    'Carro': '#4CAF50',
    'Moto': '#F44336',
    'Caminhão': '#FF9800'
}

# ========== CONTADOR POR ID ÚNICO ==========
class UniqueVehicleCounter:
    def __init__(self):
        self.seen_ids = set()
        self.timeline = []
        self.class_counts = {'Carro': 0, 'Moto': 0, 'Caminhão': 0}
        self.class_timeline = {'Carro': [], 'Moto': [], 'Caminhão': []}

    def add_new_ids(self, current_ids, class_info=None):
        new_ids = [vid for vid in current_ids if vid not in self.seen_ids]

        for vid in new_ids:
            self.seen_ids.add(vid)
            if class_info and vid in class_info:
                vehicle_type = class_info[vid]
                if vehicle_type in self.class_counts:
                    self.class_counts[vehicle_type] += 1

        if new_ids:
            current_time = time.time()
            self.timeline.append((current_time, len(new_ids)))

            for vehicle_type in self.class_counts:
                count = sum(1 for vid in new_ids if class_info and class_info.get(vid) == vehicle_type)
                if count > 0:
                    self.class_timeline[vehicle_type].append((current_time, count))

        return len(new_ids), len(self.seen_ids)

    def get_cumulative_data(self):
        if not self.timeline:
            return [], []
        start_time = self.timeline[0][0]
        times = [t - start_time for t, c in self.timeline]
        counts = np.cumsum([c for t, c in self.timeline])
        return times, counts

    def get_class_cumulative_data(self, vehicle_type):
        if vehicle_type not in self.class_timeline or not self.class_timeline[vehicle_type]:
            return [], []
        start_time = self.timeline[0][0] if self.timeline else 0
        timeline = self.class_timeline[vehicle_type]
        times = [t - start_time for t, c in timeline]
        counts = np.cumsum([c for t, c in timeline])
        return times, counts

# ========== FUNÇÕES AUXILIARES ==========
def load_model():
    import sys
    from pathlib import Path
    
    # Detecta se está rodando como .exe ou .py
    if getattr(sys, 'frozen', False):
        # Rodando como .exe - PyInstaller extrai aqui
        base_path = sys._MEIPASS
    else:
        # Rodando como .py normal
        base_path = Path(__file__).parent
    
    model_path = Path(base_path) / "yolov8n.pt"
    return YOLO(str(model_path))

def get_youtube_stream_url(url):
    """Obtém URL de stream direto do YouTube - CORRIGIDO"""
    ydl_opts = {
        'format': 'best[height<=720]/best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'url' in info:
                return info['url']
            elif 'manifest_url' in info:
                return info['manifest_url']
            elif 'formats' in info and len(info['formats']) > 0:
                return info['formats'][0]['url']
            else:
                print("Erro: Nenhuma URL de stream encontrada")
                return None
    except Exception as e:
        print(f"Erro ao obter stream: {e}")
        return None

# ========== WORKER DE VÍDEO ==========
class VideoWorker(QObject):
    frame_ready = Signal(np.ndarray)
    stats_updated = Signal(int, int)
    graph_data_ready = Signal(object, object, dict)
    processing_finished = Signal()
    error_occurred = Signal(str)
    vehicle_distribution = Signal(dict)
    fps_updated = Signal(float)

    def __init__(self, video_path, source_type, youtube_url, frame_skip):
        super().__init__()
        self.video_path_input = video_path
        self.source_type = source_type
        self.youtube_url = youtube_url
        self.frame_skip = frame_skip
        self._is_running = True

    @Slot()
    def run(self):
        try:
            video_path = self.video_path_input

            if self.source_type == "YouTube" and self.youtube_url:
                stream_url = get_youtube_stream_url(self.youtube_url)
                if not stream_url:
                    raise ValueError("Não foi possível obter stream do YouTube")
                video_path = stream_url

            if not video_path:
                raise ValueError("Caminho de vídeo inválido")

            model = load_model()
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                raise ValueError("Não foi possível abrir o vídeo")

            counter = UniqueVehicleCounter()
            last_graph_update = time.time()
            last_fps_update = time.time()
            fps_counter = 0
            yolo_classes_to_track = [2, 3, 5, 7]

            while cap.isOpened() and self._is_running:
                ret, frame = cap.read()
                if not ret:
                    break

                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                if self.frame_skip > 0 and current_frame % (self.frame_skip + 1) != 0:
                    continue

                results = model.track(frame, classes=yolo_classes_to_track, persist=True, verbose=False)
                current_ids = set()
                class_info = {}

                if results[0].boxes.id is not None:
                    boxes = results[0].boxes
                    classes = results[0].boxes.cls.tolist()

                    for box, obj_id, cls_id in zip(boxes.xyxy, boxes.id, classes):
                        x1, y1, x2, y2 = map(int, box)
                        track_id = int(obj_id)
                        current_ids.add(track_id)

                        simple_class = SIMPLE_VEHICLE_MAP.get(int(cls_id))
                        class_info[track_id] = simple_class
                        class_name = VEHICLE_CLASSES.get(int(cls_id), 'Veículo')

                        color = (0, 255, 0) if simple_class == 'Carro' else \
                                (255, 100, 0) if simple_class == 'Moto' else (0, 150, 255)

                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)

                        label = f"ID {track_id} - {class_name}"
                        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                        cv2.rectangle(frame, (x1, y1 - h - 10), (x1 + w, y1), color, -1)
                        cv2.putText(frame, label, (x1, y1 - 5),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                new_count, total_unique = counter.add_new_ids(current_ids, class_info)
                distribution = counter.class_counts.copy()

                fps_counter += 1
                if time.time() - last_fps_update > 1.0:
                    fps = fps_counter / (time.time() - last_fps_update)
                    self.fps_updated.emit(fps)
                    fps_counter = 0
                    last_fps_update = time.time()

                self.frame_ready.emit(frame)
                self.stats_updated.emit(total_unique, new_count)
                self.vehicle_distribution.emit(distribution)

                if time.time() - last_graph_update > 2.0:
                    times, counts = counter.get_cumulative_data()
                    class_data = {}
                    for vtype in ['Carro', 'Moto', 'Caminhão']:
                        t, c = counter.get_class_cumulative_data(vtype)
                        class_data[vtype] = (t, c)

                    if len(times) > 0:
                        self.graph_data_ready.emit(times, counts, class_data)
                    last_graph_update = time.time()

            cap.release()

        except Exception as e:
            self.error_occurred.emit(f"Erro no processamento: {str(e)}")
        finally:
            self.processing_finished.emit()

    def stop(self):
        self._is_running = False

# ========== WIDGET DE ESTATÍSTICAS ==========
class StatsCard(QFrame):
    def __init__(self, title, icon, color):
        super().__init__()
        self.setObjectName("StatsCard")
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)

        title_layout = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 28px; color: {color};")
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; color: #888;")

        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.value_label = QLabel("0")
        self.value_label.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {color};")

        layout.addLayout(title_layout)
        layout.addWidget(self.value_label)
        layout.addStretch()

        self.setLayout(layout)

    def set_value(self, value):
        self.value_label.setText(str(value))

# ========== WIDGET DE GRÁFICO DE PIZZA PYQTGRAPH ==========
class DonutChartWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("📊 Distribuição por Tipo")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00d9ff;")
        self.layout.addWidget(title)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.hideAxis('bottom')
        self.plot_widget.hideAxis('left')
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.setMouseEnabled(False, False)

        self.layout.addWidget(self.plot_widget)

        self.legend_layout = QHBoxLayout()
        self.legend_layout.setSpacing(20)
        self.legend_labels = {}

        for vtype, color in VEHICLE_COLORS.items():
            label = QLabel(f"● {vtype}: 0")
            label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
            self.legend_labels[vtype] = label
            self.legend_layout.addWidget(label)

        self.layout.addLayout(self.legend_layout)
        self.setLayout(self.layout)

        self.data = {'Carro': 0, 'Moto': 0, 'Caminhão': 0}

    def update_data(self, data):
        self.data = data
        total = sum(data.values())

        for vtype, count in data.items():
            pct = (count / total * 100) if total > 0 else 0
            self.legend_labels[vtype].setText(f"● {vtype}: {count} ({pct:.1f}%)")

        self.plot_widget.clear()

        if total == 0:
            return

        outer_radius = 1.0
        inner_radius = 0.6

        start_angle = 0
        colors = [(76, 175, 80), (244, 67, 54), (255, 152, 0)]
        order = ['Carro', 'Moto', 'Caminhão']

        for i, vtype in enumerate(order):
            count = data[vtype]
            if count == 0:
                continue

            angle = (count / total) * 360

            theta = np.linspace(np.deg2rad(start_angle), 
                              np.deg2rad(start_angle + angle), 100)

            x_outer = outer_radius * np.cos(theta)
            y_outer = outer_radius * np.sin(theta)

            x_inner = inner_radius * np.cos(theta)
            y_inner = inner_radius * np.sin(theta)

            x = np.concatenate([x_outer, x_inner[::-1]])
            y = np.concatenate([y_outer, y_inner[::-1]])

            brush = pg.mkBrush(colors[i])
            pen = pg.mkPen(color=(30, 30, 30), width=2)
            self.plot_widget.plot(x, y, fillLevel=0, brush=brush, pen=pen)

            start_angle += angle

        theta_center = np.linspace(0, 2*np.pi, 100)
        x_center = inner_radius * np.cos(theta_center)
        y_center = inner_radius * np.sin(theta_center)
        self.plot_widget.plot(x_center, y_center, fillLevel=0, 
                             brush=pg.mkBrush((30, 30, 30)), 
                             pen=pg.mkPen(None))

# ========== JANELA PRINCIPAL ==========
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚗 Vehicle Tracker Pro - Streaming Simplificado")
        self.setGeometry(50, 50, 1600, 900)
        self.video_path = None
        self.worker_thread = None
        self.video_worker = None
        self.init_ui()
        self.apply_professional_stylesheet()

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(80)
        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()
        title = QLabel("🚗 Vehicle Tracker Pro")
        title.setObjectName("HeaderTitle")
        subtitle = QLabel("Sistema Simplificado - Upload Local ou YouTube Streaming")
        subtitle.setObjectName("HeaderSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.fps_label = QLabel("FPS: --")
        self.fps_label.setObjectName("FPSLabel")
        header_layout.addWidget(self.fps_label)

        header.setLayout(header_layout)
        main_layout.addWidget(header)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)

        left_panel = QFrame()
        left_panel.setObjectName("LeftPanel")
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout()
        left_layout.setSpacing(20)

        tabs = QTabWidget()
        tabs.setObjectName("ConfigTabs")

        source_tab = QWidget()
        source_layout = QVBoxLayout()
        source_layout.setSpacing(15)

        source_group = QGroupBox("📹 Fonte do Vídeo")
        source_group.setObjectName("ConfigGroup")
        source_inner = QVBoxLayout()

        self.radio_upload = QRadioButton("📁 Arquivo Local")
        self.radio_youtube = QRadioButton("🌐 YouTube (Streaming Direto)")
        self.radio_upload.setChecked(True)

        source_inner.addWidget(self.radio_upload)
        source_inner.addWidget(self.radio_youtube)
        source_group.setLayout(source_inner)
        source_layout.addWidget(source_group)

        upload_group = QGroupBox("Arquivo Local")
        upload_group.setObjectName("ConfigGroup")
        upload_layout = QVBoxLayout()

        self.btn_select_file = QPushButton("📂 Selecionar Vídeo")
        self.btn_select_file.setObjectName("PrimaryButton")
        self.btn_select_file.clicked.connect(self.select_file)

        self.selected_file_label = QLabel("Nenhum arquivo selecionado")
        self.selected_file_label.setObjectName("InfoLabel")
        self.selected_file_label.setWordWrap(True)

        upload_layout.addWidget(self.btn_select_file)
        upload_layout.addWidget(self.selected_file_label)
        upload_group.setLayout(upload_layout)
        source_layout.addWidget(upload_group)

        youtube_group = QGroupBox("YouTube Streaming")
        youtube_group.setObjectName("ConfigGroup")
        youtube_layout = QVBoxLayout()

        self.youtube_input = QLineEdit()
        self.youtube_input.setPlaceholderText("Cole o link do YouTube aqui...")
        self.youtube_input.setEnabled(False)

        info_label = QLabel("ℹ️ Sempre usa streaming direto (não baixa o vídeo)")
        info_label.setStyleSheet("color: #00d9ff; font-size: 11px; font-style: italic;")

        youtube_layout.addWidget(QLabel("URL do vídeo:"))
        youtube_layout.addWidget(self.youtube_input)
        youtube_layout.addWidget(info_label)
        youtube_group.setLayout(youtube_layout)
        source_layout.addWidget(youtube_group)

        self.radio_upload.toggled.connect(self.toggle_source_controls)

        source_layout.addStretch()
        source_tab.setLayout(source_layout)

        perf_tab = QWidget()
        perf_layout = QVBoxLayout()
        perf_layout.setSpacing(15)

        perf_group = QGroupBox("⚙️ Otimização de Performance")
        perf_group.setObjectName("ConfigGroup")
        perf_inner = QVBoxLayout()

        skip_label = QLabel("Pular frames (↑ performance, ↓ precisão)")
        self.frame_skip_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_skip_slider.setRange(0, 10)
        self.frame_skip_slider.setValue(2)
        self.frame_skip_slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        self.frame_skip_value = QLabel("2")
        self.frame_skip_slider.valueChanged.connect(
            lambda v: self.frame_skip_value.setText(str(v))
        )

        perf_inner.addWidget(skip_label)
        perf_inner.addWidget(self.frame_skip_slider)
        perf_inner.addWidget(self.frame_skip_value, alignment=Qt.AlignmentFlag.AlignCenter)
        perf_group.setLayout(perf_inner)
        perf_layout.addWidget(perf_group)

        perf_layout.addStretch()
        perf_tab.setLayout(perf_layout)

        tabs.addTab(source_tab, "📹 Fonte")
        tabs.addTab(perf_tab, "⚙️ Performance")

        left_layout.addWidget(tabs)

        self.btn_process = QPushButton("▶️ INICIAR PROCESSAMENTO")
        self.btn_process.setObjectName("ProcessButton")
        self.btn_process.setMinimumHeight(50)
        self.btn_process.clicked.connect(self.start_processing)

        left_layout.addWidget(self.btn_process)
        left_panel.setLayout(left_layout)
        content_layout.addWidget(left_panel, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setSpacing(20)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)

        self.card_total = StatsCard("Total de Veículos", "🚗", "#4CAF50")
        self.card_new = StatsCard("Novos Detectados", "✨", "#2196F3")

        stats_layout.addWidget(self.card_total)
        stats_layout.addWidget(self.card_new)
        right_layout.addLayout(stats_layout)

        video_container = QFrame()
        video_container.setObjectName("VideoContainer")
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_label = QLabel("Aguardando vídeo...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setObjectName("VideoDisplay")
        self.video_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        video_layout.addWidget(self.video_label)
        video_container.setLayout(video_layout)
        right_layout.addWidget(video_container, 2)

        graphs_layout = QHBoxLayout()
        graphs_layout.setSpacing(15)

        graph_container = QFrame()
        graph_container.setObjectName("GraphContainer")
        graph_layout = QVBoxLayout()
        graph_layout.setContentsMargins(10, 10, 10, 10)

        graph_title = QLabel("📈 Detecções Acumuladas")
        graph_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00d9ff;")
        graph_layout.addWidget(graph_title)

        self.graph_widget = pg.PlotWidget()
        self.graph_widget.setBackground('#1e1e1e')
        self.graph_widget.setLabel('left', 'Veículos Únicos', color='#ccc', size='12pt')
        self.graph_widget.setLabel('bottom', 'Tempo (segundos)', color='#ccc', size='12pt')
        self.graph_widget.showGrid(x=True, y=True, alpha=0.3)
        self.graph_widget.setMouseEnabled(x=True, y=True)

        self.plot_line_total = self.graph_widget.plot([], [], pen=pg.mkPen('#00d9ff', width=3), 
                                                       name='Total')
        self.plot_line_car = self.graph_widget.plot([], [], pen=pg.mkPen('#4CAF50', width=2), 
                                                     name='Carros')
        self.plot_line_moto = self.graph_widget.plot([], [], pen=pg.mkPen('#F44336', width=2), 
                                                      name='Motos')
        self.plot_line_truck = self.graph_widget.plot([], [], pen=pg.mkPen('#FF9800', width=2), 
                                                       name='Caminhões')

        self.graph_widget.addLegend()

        graph_layout.addWidget(self.graph_widget)
        graph_container.setLayout(graph_layout)
        graphs_layout.addWidget(graph_container, 2)

        self.donut_chart = DonutChartWidget()
        self.donut_chart.setObjectName("GraphContainer")
        self.donut_chart.setMaximumWidth(400)
        graphs_layout.addWidget(self.donut_chart, 1)

        right_layout.addLayout(graphs_layout, 2)

        right_panel.setLayout(right_layout)
        content_layout.addWidget(right_panel, 3)

        main_layout.addLayout(content_layout)

        status_bar = QFrame()
        status_bar.setObjectName("StatusBar")
        status_bar.setFixedHeight(40)
        status_layout = QHBoxLayout()

        self.status_label = QLabel("⏸️ Aguardando entrada...")
        self.status_label.setObjectName("StatusLabel")
        status_layout.addWidget(self.status_label)

        status_bar.setLayout(status_layout)
        main_layout.addWidget(status_bar)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def apply_professional_stylesheet(self):
        self.setStyleSheet("""
            * { font-family: 'Segoe UI', Arial, sans-serif; }
            QMainWindow { background: #0f0f0f; }
            #Header {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a1a2e, stop:1 #16213e);
                border-bottom: 3px solid #0f3460;
            }
            #HeaderTitle { font-size: 28px; font-weight: bold; color: #00d9ff; padding-left: 20px; }
            #HeaderSubtitle { font-size: 14px; color: #a0a0a0; padding-left: 20px; }
            #FPSLabel {
                font-size: 16px; font-weight: bold; color: #00ff88;
                background: rgba(0, 255, 136, 0.1); padding: 8px 20px;
                border-radius: 20px; margin-right: 20px;
            }
            #LeftPanel { background: #1a1a1a; border-radius: 15px; padding: 20px; }
            #ConfigTabs::pane { border: 2px solid #2d2d2d; border-radius: 10px; background: #1e1e1e; }
            #ConfigTabs QTabBar::tab {
                background: #252525; color: #888; padding: 12px 20px; margin-right: 5px;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
            }
            #ConfigTabs QTabBar::tab:selected { background: #1e1e1e; color: #00d9ff; font-weight: bold; }
            #ConfigGroup {
                background: #252525; border: 2px solid #333; border-radius: 10px;
                padding: 15px; margin: 5px; font-weight: bold; color: #00d9ff;
            }
            #ConfigGroup::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 5px 10px; color: #00d9ff; }
            QPushButton {
                background: #2d2d2d; color: white; border: 2px solid #444;
                border-radius: 8px; padding: 10px; font-weight: bold;
            }
            QPushButton:hover { background: #3d3d3d; border-color: #00d9ff; }
            #PrimaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0066cc, stop:1 #0088ff);
                border: none;
            }
            #PrimaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0077dd, stop:1 #0099ff);
            }
            #ProcessButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00c853, stop:1 #00e676);
                color: white; font-size: 16px; border: none; border-radius: 10px;
            }
            #ProcessButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d861, stop:1 #00f787);
            }
            #ProcessButton:disabled { background: #444; color: #888; }
            QLineEdit {
                background: #2d2d2d; border: 2px solid #444; border-radius: 6px;
                padding: 8px; color: white; font-size: 13px;
            }
            QLineEdit:focus { border-color: #00d9ff; }
            QRadioButton { color: #ccc; spacing: 8px; padding: 5px; }
            QRadioButton::indicator { width: 18px; height: 18px; }
            QRadioButton::indicator:checked {
                background: #00d9ff; border: 3px solid #006080; border-radius: 9px;
            }
            QSlider::groove:horizontal { height: 8px; background: #2d2d2d; border-radius: 4px; }
            QSlider::handle:horizontal { background: #00d9ff; width: 20px; margin: -6px 0; border-radius: 10px; }
            #StatsCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d2d2d, stop:1 #1e1e1e);
                border: 2px solid #333; border-radius: 15px; min-height: 120px;
            }
            #VideoContainer { background: #000; border: 3px solid #333; border-radius: 15px; }
            #VideoDisplay { background: #000; color: #666; font-size: 18px; }
            #GraphContainer { background: #1e1e1e; border: 2px solid #333; border-radius: 15px; padding: 10px; }
            #StatusBar { background: #1a1a1a; border-top: 2px solid #333; }
            #StatusLabel { color: #00ff88; font-size: 14px; font-weight: bold; padding-left: 20px; }
            #InfoLabel { color: #888; font-size: 12px; font-style: italic; }
            QLabel { color: #ccc; }
        """)

    @Slot()
    def toggle_source_controls(self):
        is_upload = self.radio_upload.isChecked()
        self.btn_select_file.setEnabled(is_upload)
        self.youtube_input.setEnabled(not is_upload)

    @Slot()
    def select_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Selecione um vídeo", "",
            "Vídeos (*.mp4 *.avi *.mov *.mkv *.mpeg4);;Todos os arquivos (*.*)"
        )
        if file_name:
            self.video_path = file_name
            self.selected_file_label.setText(f"✓ {Path(file_name).name}")
            self.selected_file_label.setStyleSheet("color: #00ff88;")

    @Slot()
    def start_processing(self):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            QMessageBox.warning(self, "Aviso", "Processamento já em andamento!")
            return

        source_type = "Upload" if self.radio_upload.isChecked() else "YouTube"
        youtube_url = self.youtube_input.text().strip()
        frame_skip = self.frame_skip_slider.value()

        if source_type == "Upload" and (not self.video_path or not os.path.exists(self.video_path)):
            QMessageBox.critical(self, "Erro", "Selecione um arquivo de vídeo válido!")
            return

        if source_type == "YouTube" and not youtube_url:
            QMessageBox.critical(self, "Erro", "Insira um link do YouTube válido!")
            return

        self.btn_process.setText("⏹️ PARAR PROCESSAMENTO")
        self.btn_process.clicked.disconnect()
        self.btn_process.clicked.connect(self.stop_processing)
        self.status_label.setText("▶️ Iniciando processamento...")

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
        self.video_worker.vehicle_distribution.connect(self.update_vehicle_distribution)
        self.video_worker.fps_updated.connect(self.update_fps)
        self.video_worker.processing_finished.connect(self.processing_finished)
        self.video_worker.error_occurred.connect(self.processing_error)

        self.worker_thread.start()

    @Slot()
    def stop_processing(self):
        if self.video_worker:
            self.video_worker.stop()
            self.status_label.setText("⏹️ Parando processamento...")

    @Slot(np.ndarray)
    def update_video_frame(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(q_image).scaled(
            self.video_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    @Slot(int, int)
    def update_stats(self, total_unique, new_count):
        self.card_total.set_value(total_unique)
        self.card_new.set_value(new_count)
        self.status_label.setText(f"▶️ Processando... | Total: {total_unique} | Novos: {new_count}")

    @Slot(object, object, dict)
    def update_graph(self, times, counts, class_data):
        if len(times) > 0:
            self.plot_line_total.setData(times, counts)

            for vtype, color in [('Carro', '#4CAF50'), ('Moto', '#F44336'), ('Caminhão', '#FF9800')]:
                t, c = class_data.get(vtype, ([], []))
                if len(t) > 0:
                    if vtype == 'Carro':
                        self.plot_line_car.setData(t, c)
                    elif vtype == 'Moto':
                        self.plot_line_moto.setData(t, c)
                    elif vtype == 'Caminhão':
                        self.plot_line_truck.setData(t, c)

    @Slot(dict)
    def update_vehicle_distribution(self, distribution):
        self.donut_chart.update_data(distribution)

    @Slot(float)
    def update_fps(self, fps):
        self.fps_label.setText(f"FPS: {fps:.1f}")

    @Slot()
    def processing_finished(self):
        self.status_label.setText("✅ Processamento concluído com sucesso!")
        self.btn_process.setText("▶️ INICIAR PROCESSAMENTO")
        self.btn_process.clicked.disconnect()
        self.btn_process.clicked.connect(self.start_processing)
        self.cleanup_thread()

    @Slot(str)
    def processing_error(self, error_message):
        QMessageBox.critical(self, "Erro no Processamento", error_message)
        self.status_label.setText(f"❌ Erro: {error_message}")
        self.btn_process.setText("▶️ INICIAR PROCESSAMENTO")
        self.btn_process.clicked.disconnect()
        self.btn_process.clicked.connect(self.start_processing)
        self.cleanup_thread()

    def cleanup_thread(self):
        if self.worker_thread is not None:
            if self.video_worker:
                self.video_worker.stop()
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
            self.video_worker = None

    def closeEvent(self, event):
        if self.video_worker:
            self.video_worker.stop()
        self.cleanup_thread()
        event.accept()

# ========== EXECUÇÃO ==========
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(15, 15, 15))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
