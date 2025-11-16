# Introdução à Visão Computacional com Python e OpenCV

## 👥 Integrantes do Grupo
- **Nome Completo**: [Seu Nome Aqui]  
- **Matrícula**: [Sua Matrícula Aqui]

---

## 📌 Descrição do Projeto

Este trabalho implementa o projeto de **Rastreamento de Objetos** (Object Tracking) com base no tutorial do canal Pysource, mas com **melhorias significativas** que elevam o nível funcional, técnico e visual, visando a **nota máxima** no sistema de ranqueamento da turma.

O sistema permite:
- Processar **vídeos locais** ou **links do YouTube** (com download automático)
- Detectar **qualquer tipo de veículo** (carro, caminhão, moto, ônibus) usando **YOLOv8**
- Rastrear objetos com **IDs únicos e persistentes**
- Contar veículos **por ID único** (não por frame)
- Exibir **gráfico em tempo real** com contagem acumulada
- Interface web interativa via **Streamlit**

---

## 🛠️ Tecnologias Utilizadas

- **Python 3.12**
- **OpenCV** – processamento de vídeo
- **YOLOv8 (Ultralytics)** – detecção de objetos com IA
- **Streamlit** – interface web
- **yt-dlp** – extração de vídeos do YouTube
- **Matplotlib** – gráficos em tempo real

---

## ▶️ Instruções de Instalação e Execução

### 1. Clone o repositório
```bash
git clone https://github.com/Jvgamer984/computer-vision-projects.git
cd computer-vision-projects
python -m venv venv
source venv/bin/activate 
pip install -r requirements.txt