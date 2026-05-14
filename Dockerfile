FROM jrottenberg/ffmpeg:6.0-nvidia

# Anular el ENTRYPOINT heredado de la imagen base
ENTRYPOINT []

# Instalar Python, pip y tzdata para soporte de zona horaria
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 --version && python3 --version
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel
RUN pip3 install --no-cache-dir -r requirements.txt
RUN python3 -c "import flask_cors; print('flask_cors imported successfully')"

COPY app.py .
COPY src/ ./src/
COPY diagnose_routes.py .

ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

EXPOSE 8080

RUN mkdir -p /shared/uploads /shared/outputs /shared/input /tmp/audios /tmp/videos /tmp/images /tmp/data /tmp/data/cache  && \
    chmod -R 777 /shared/uploads /shared/outputs /shared/input /tmp/audios /tmp/videos /tmp/images /tmp/data /tmp/data/cache

# El diagnóstico se ejecutará al iniciar el contenedor

# Ejecutar diagnóstico y luego la API Flask
CMD ["sh", "-c", "echo '🔍 Ejecutando diagnóstico...' && python3 /app/diagnose_routes.py && echo '✅ Diagnóstico completado, iniciando aplicación...' && python3 /app/app.py"]
