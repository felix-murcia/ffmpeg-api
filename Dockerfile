FROM jrottenberg/ffmpeg:6.0-nvidia

# Anular el ENTRYPOINT heredado de la imagen base
ENTRYPOINT []

# Instalar Python y pip
RUN apt-get update && apt-get install -y python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app.py .
COPY src/ ./src/

ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

EXPOSE 8080

RUN mkdir -p /shared/uploads /shared/outputs /shared/input /tmp/audios

# Ejecutar tu API Flask
CMD ["python3", "/app/app.py"]
