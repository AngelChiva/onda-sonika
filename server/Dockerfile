FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py tune.py moderar.py ./
# descarga el modelo de voz a texto dentro de la imagen (gratis, funciona sin internet)
RUN python -c "from faster_whisper import WhisperModel;WhisperModel('base',device='cpu',compute_type='int8',download_root='/models')"
# precalienta numba/librosa para que el primer autotune no tarde
RUN python -c "import numpy as np,tune;tune.autotune((np.sin(np.arange(22050)/22050*2*np.pi*220)*.3).astype('float32'),22050)"
ENV DATA_DIR=/data
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port 9443 --ssl-keyfile /certs/ssl.key --ssl-certfile /certs/ssl.crt --proxy-headers"]
