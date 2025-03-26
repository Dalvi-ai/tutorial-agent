import os
from dotenv import load_dotenv
import yt_dlp
import cv2
import openai
import re
import asyncio
import concurrent.futures
import json
import subprocess
import langchain
from langchain_openai import ChatOpenAI
from paddleocr import PaddleOCR
from moviepy.editor import VideoFileClip
import sys
from pathlib import Path

# Load environment variables from .env file
load_dotenv(override=True)

# Configure OpenAI
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")
openai.api_key = api_key

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.absolute()

# Função para baixar vídeo do YouTube
def baixar_video(url, output_folder="videos"):
    output_folder = os.path.join(PROJECT_ROOT, output_folder)
    os.makedirs(output_folder, exist_ok=True)
    output_path = os.path.join(output_folder, f"{url.split('=')[-1]}.mp4")
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': output_path,
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        print(f"Error downloading video: {e}")
        raise

# Função para extrair frames do vídeo
def extrair_frames(video_path, frame_rate=1):
    output_folder = os.path.join(PROJECT_ROOT, "frames", os.path.basename(video_path).split('.')[0])
    os.makedirs(output_folder, exist_ok=True)

    try:
        clip = VideoFileClip(video_path)
        duration = int(clip.duration)
        clip.close()

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)

        for i in range(0, duration, frame_rate):
            frame_time = i * fps
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_time)
            success, frame = cap.read()
            if success:
                filename = os.path.join(output_folder, f"frame_{i}.png")
                cv2.imwrite(filename, frame)

        cap.release()
        return output_folder
    except Exception as e:
        print(f"Error extracting frames: {e}")
        raise

# Função para extrair texto das imagens usando OpenAI Vision
def extrair_texto_com_openai(image_path):
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()

    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[
            {"role": "system", "content": "Extraia o código da imagem e entenda a estrutura do projeto."},
            {"role": "user", "content": image_data}
        ]
    )
    return response["choices"][0]["message"]["content"]

# Função para extrair texto com OCR (fallback)
def extrair_texto_com_ocr(image_path):
    ocr = PaddleOCR(use_angle_cls=True, lang="en")
    results = ocr.ocr(image_path, cls=True)
    
    texto_extraido = "\n".join([line[1][0] for line in results[0]])
    return texto_extraido

# Função para organizar código extraído em arquivos e pastas
def organizar_codigo(texto):
    prompt = f"""
    Analise o seguinte texto extraído de um tutorial de programação:

    {texto}

    Gere um JSON contendo:
    - "folders": Uma lista de pastas necessárias para o projeto.
    - "files": Um dicionário onde cada chave é um caminho de arquivo e o valor é o código correspondente.
    - "dependencies": Uma lista de dependências a serem instaladas.
    - "deploy_steps": Instruções para rodar o projeto.

    Exemplo de saída:
    {{
        "folders": ["src", "src/components", "public"],
        "files": {{
            "src/main.js": "console.log('Hello World');",
            "package.json": "{{ 'name': 'app', 'dependencies': {{}} }}"
        }},
        "dependencies": ["react", "express"],
        "deploy_steps": "Execute npm install e npm start para rodar o projeto."
    }}
    """
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[{"role": "system", "content": "Você é um organizador de código extraído de vídeos."},
                  {"role": "user", "content": prompt}]
    )
    return json.loads(response["choices"][0]["message"]["content"])

# Função para criar estrutura de pastas e arquivos
def criar_projeto(structure, project_name="meu_projeto"):
    os.makedirs(project_name, exist_ok=True)

    # Criar pastas
    for folder in structure["folders"]:
        os.makedirs(os.path.join(project_name, folder), exist_ok=True)

    # Criar arquivos
    for file_path, content in structure["files"].items():
        file_full_path = os.path.join(project_name, file_path)
        with open(file_full_path, "w") as f:
            f.write(content)

    # Criar README com instruções
    with open(os.path.join(project_name, "README.md"), "w") as f:
        f.write(f"# Como rodar o projeto\n\n{structure['deploy_steps']}\n\n## Dependências\n\n")
        f.write("\n".join([f"- {dep}" for dep in structure["dependencies"]]))

# Função para abrir o VSCode automaticamente
def abrir_vscode(project_path="meu_projeto"):
    try:
        project_path = os.path.join(PROJECT_ROOT, project_path)
        if sys.platform == "win32":
            subprocess.run(["code", project_path], shell=True)
        else:
            subprocess.run(["code", project_path])
    except Exception as e:
        print(f"Error opening VSCode: {e}")
        print("Please open the project manually in VSCode")

# Função assíncrona para processar um único vídeo
async def processar_video(url):
    print(f"🔽 Baixando vídeo {url}...")
    video_path = baixar_video(url)

    print(f"🎬 Extraindo frames do vídeo {url}...")
    frames_folder = extrair_frames(video_path)

    texto_total = []
    for frame in sorted(os.listdir(frames_folder)):
        frame_path = os.path.join(frames_folder, frame)
        print(f"📷 Processando {frame}...")

        try:
            texto_extraido = extrair_texto_com_openai(frame_path)
        except:
            print("❌ OpenAI falhou, tentando PaddleOCR...")
            texto_extraido = extrair_texto_com_ocr(frame_path)

        texto_total.append(texto_extraido)

    texto_final = "\n".join(texto_total)
    estrutura = organizar_codigo(texto_final)

    print("📂 Criando estrutura de projeto...")
    criar_projeto(estrutura)

    print("🚀 Abrindo no VSCode...")
    abrir_vscode()

# Função principal para processar vários vídeos simultaneamente
async def processar_varios_videos(urls):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        await asyncio.gather(*[loop.run_in_executor(executor, processar_video, url) for url in urls])

# 🚀 Lista de vídeos a serem processados
urls_dos_videos = [
    "https://www.youtube.com/watch?v=XkOXNlHJP6M&list=WL&index=9",
    "https://www.youtube.com/watch?v=3R63m4sTpKo&list=WL&index=6"
]

# Rodar a extração para múltiplos vídeos
asyncio.run(processar_varios_videos(urls_dos_videos))
