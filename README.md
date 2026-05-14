# FFmpeg CUDA API

API REST para procesamiento de video y audio con aceleración GPU mediante FFmpeg y NVIDIA CUDA.

## Requisitos

- Python 3.8+
- FFmpeg con soporte para NVENC (compilación con CUDA)
- NVIDIA GPU con drivers instalados
- Docker (opcional)

## Estructura del Proyecto

```
ffmpeg-cuda/
├── app.py                        # Punto de entrada principal
├── src/
│   └── modules/                  # Módulos de la aplicación
│       ├── __init__.py           # Exports públicos
│       ├── config.py             # Configuración de Flask
│       ├── utils.py              # Utilidades generales
│       ├── gpu.py                # Detección de GPU y configuración
│       ├── process_manager.py    # Gestión de procesos
│       ├── ffmpeg_runner.py      # Ejecutor de FFmpeg
│       ├── audio_routes.py       # Endpoints de audio
│       ├── video_routes.py       # Endpoints de video
│       └── video_helper/         # Helpers para video (SOLID)
│           ├── __init__.py
│           ├── file_handler.py   # Manejo de archivos
│           ├── ffmpeg_executor.py# Ejecución de comandos FFmpeg
│           ├── video_optimizer.py# Optimización de video
│           └── video_creator.py  # Creación de video desde audio+imagen
├── docker-compose.yml            # Orquestación Docker
├── Dockerfile                    # Imagen del contenedor
├── requirements.txt              # Dependencias Python
└── README.md                     # Documentación
```

## Módulos

### [`config.py`](src/modules/config.py)

Módulo de configuración de la aplicación Flask. Proporciona:

- [`create_app()`](src/modules/config.py:9) - Crea y configura la aplicación Flask con CORS
- [`get_app()`](src/modules/config.py:31) - Obtiene la instancia global de la aplicación
- [`get_logger()`](src/modules/config.py:39) - Obtiene el logger de la aplicación

### [`utils.py`](src/modules/utils.py)

Utilidades generales para el proyecto:

- [`format_duration(seconds)`](src/modules/utils.py:6) - Formatea segundos a formato `HH:MM:SS`

### [`gpu.py`](src/modules/gpu.py)

Módulo de detección automática de GPU NVIDIA y configuración de presets:

- [`get_gpu_preset_and_level()`](src/modules/gpu.py:10) - Detecta la GPU y devuelve la configuración óptima

**Presets soportados:**

| GPU | Preset | Level | Multipass | Lookahead |
|-----|--------|-------|-----------|-----------|
| Maxwell (9xxM) | p4 | ❌ | none | 16 |
| Pascal (10xx) | p6 | ✅ 4.1 | fullres | 32 |
| Turing/Ampere (20xx-40xx) | p7 | ✅ 4.1 | fullres | 32 |
| Sin GPU | p4 | ❌ | none | 16 |

### [`process_manager.py`](src/modules/process_manager.py)

Gestor de procesos activos con almacenamiento en memoria y persistencia en archivos:

- [`ProcessManager`](src/modules/process_manager.py:12) - Clase principal para gestionar procesos
- [`get_process_manager()`](src/modules/process_manager.py:92) - Obtiene la instancia global del gestor

**Métodos:**
- `get(process_id)` - Obtiene un proceso por su ID
- `set(process_id, data)` - Establece los datos de un proceso
- `update(process_id, status, **kwargs)` - Actualiza el estado del proceso
- `get_from_file(process_id)` - Lee el proceso desde archivo
- `save_to_file(process_id, data)` - Guarda el estado en archivo
- `list_active()` - Lista los procesos activos

### [`ffmpeg_runner.py`](src/modules/ffmpeg_runner.py)

Ejecutor de FFmpeg en segundo plano con cálculo de progreso:

- [`run_ffmpeg(process_id, cmd)`](src/modules/ffmpeg_runner.py:16) - Ejecuta un comando FFmpeg y calcula el progreso

**Funcionalidades:**
- Ejecución en proceso separado (multiprocessing)
- Cálculo de progreso basado en duración total
- Logging en tiempo real
- Persistencia de estado en archivos JSON

### [`video_routes.py`](src/modules/video_routes.py)

Endpoints REST para procesamiento de video:

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Health check del servicio |
| `/gpu-status` | GET | Verificar disponibilidad de GPU |
| `/optimize` | POST | Iniciar optimización de video con GPU |
| `/status/<process_id>` | GET | Obtener estado de un proceso |
| `/active` | GET | Listar procesos activos |
| `/cancel/<process_id>` | POST | Cancelar un proceso |
| `/create-from-audio` | POST | Crear video a partir de audio e imagen |

**Endpoints detallados:**

#### `/health`
Health check del servicio.

```bash
curl http://localhost:8080/health
```

**Respuesta:**
```json
{
  "status": "UP",
  "service": "ffmpeg-api"
}
```

#### `/gpu-status`
Verifica la disponibilidad de GPU NVIDIA y devuelve información de la detected.

```bash
curl http://localhost:8080/gpu-status
```

**Respuesta (con GPU):**
```json
{
  "success": true,
  "gpu_available": true,
  "gpu_name": "NVIDIA GeForce RTX 3080"
}
```

**Respuesta (sin GPU):**
```json
{
  "success": true,
  "gpu_available": false
}
```

#### `/optimize`
Inicia la optimización de un video usando GPU. El proceso se ejecuta en segundo plano.

```bash
curl -X POST http://localhost:8080/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "input": "/ruta/al/video.mp4",
    "output": "/ruta/al/output_optimizado.mp4"
  }'
```

**Respuesta:**
```json
{
  "success": true,
  "process_id": "abc123def456",
  "message": "Optimización iniciada"
}
```

**Parámetros:**
- `input` (requerido): Ruta absoluta al archivo de video de entrada
- `output` (requerido): Ruta absoluta donde guardar el video optimizado

**Configuración de optimización:**
- Codec: `h264_nvenc` (NVIDIA Encoder)
- Preset: Automático según GPU detectada
- Bitrate: 1800k (variable)
- Audio: AAC 128k, 48kHz, estéreo

#### `/status/<process_id>`
Obtiene el estado actual de un proceso de optimización.

```bash
curl http://localhost:8080/status/abc123def456
```

**Respuesta:**
```json
{
  "success": true,
  "process_id": "abc123def456",
  "status": "running",
  "progress": 45.2,
  "logs": [
    "frame=  150 fps= 30 q=28.0 size=    1024kB time=00:00:05.00 bitrate=1677.1kbits/s speed=1.01x",
    "frame=  300 fps= 30 q=28.0 size=    2048kB time=00:00:10.00 bitrate=1677.1kbits/s speed=1.02x"
  ],
  "input_file": "video.mp4",
  "output_file": "output_optimizado.mp4",
  "eta_seconds": 120,
  "error": null
}
```

**Campos de estado:**
- `status`: `pending`, `running`, `completed`, `failed`, `cancelled`
- `progress`: Porcentaje de progreso (0-100)
- `logs`: Últimas 50 líneas de log del proceso
- `eta_seconds`: Tiempo estimado restante en segundos (solo si está running)
- `error`: Mensaje de error si el proceso falló

#### `/active`
Lista todos los procesos activos (pendientes o en ejecución).

```bash
curl http://localhost:8080/active
```

**Respuesta:**
```json
{
  "success": true,
  "active": {
    "abc123def456": {
      "status": "running",
      "progress": 45.2,
      "input": "/ruta/al/video.mp4",
      "output": "/ruta/al/output.mp4",
      "start_time": 1713991234.56
    }
  }
}
```

#### `/cancel/<process_id>`
Cancela un proceso en ejecución.

```bash
curl -X POST http://localhost:8080/cancel/abc123def456
```

**Respuesta:**
```json
{
  "success": true,
  "message": "Proceso cancelado"
}
```

#### `/create-from-audio`
Crea un video combinando una imagen estática con un archivo de audio. útil para generar videos para redes sociales, podcasts, o contenido audiovisual simple.

```bash
curl -X POST http://localhost:8080/create-from-audio \
  -H "Content-Type: application/json" \
  -d '{
    "audio_path": "/ruta/al/audio.mp3",
    "image_path": "/ruta/a/la/imagen.jpg"
  }'
```

**Respuesta:**
```json
{
  "success": true,
  "output_path": "/tmp/videos/video_a1b2c3d4-e5f6-7890-abcd-ef1234567890.mp4",
  "output_filename": "video_a1b2c3d4-e5f6-7890-abcd-ef1234567890.mp4",
  "image_used": "imagen.jpg",
  "audio_source": "audio.mp3"
}
```

**Parámetros:**
- `audio_path` (requerido): Ruta absoluta al archivo de audio (MP3, WAV, AAC, etc.)
- `image_path` (requerido): Ruta absoluta a la imagen de fondo (JPG, PNG, etc.)

**Configuración de video generado:**
- Resolución: 640x360 (escalado con padding para mantener aspect ratio)
- Codec video: `h264_nvenc` (si hay GPU) o `libx264` (CPU)
- Calidad: CQ 28, bitrate 300k (min), 500k (max)
- Audio: AAC 96k, 48kHz, estéreo
- Duración: Igual a la duración del audio (`-shortest`)

#### [`video_helper/`](src/modules/video_helper/)

Paquete de servicios para operaciones de video, implementado siguiendo principios SOLID y separación de responsabilidades:

##### [`file_handler.py`](src/modules/video_helper/file_handler.py)

Manejo abstracto de operaciones con archivos:

- `exists(path)` - Verifica si un archivo existe
- `mkdir(path)` - Crea directorios recursivamente
- `copy(src, dst)` - Copia archivos
- `get_filename(path)` - Extrae nombre de archivo de una ruta

##### [`ffmpeg_executor.py`](src/modules/video_helper/ffmpeg_executor.py)

Ejecutor de comandos FFmpeg con logging integrado:

- [`run_ffmpeg(cmd, timeout, check)`](src/modules/video_helper/ffmpeg_executor.py:16) - Ejecuta un comando FFmpeg
- Manejo de errores detallado con stderr/stdout
- Timeout configurable
- Verificación de éxito (check)

##### [`video_optimizer.py`](src/modules/video_helper/video_optimizer.py)

Servicio de optimización de video con GPU:

- [`launch_optimization(input_path, output_path)`](src/modules/video_helper/video_optimizer.py:30) - Inicia optimización en segundo plano
- Detecta formato de entrada y aplica codec apropiado (VP9/VP8/H.264)
- Usa presets GPU automáticos (p4/p6/p7)
- Actualiza progreso en el ProcessManager

##### [`video_creator.py`](src/modules/video_helper/video_creator.py)

Servicio para crear video desde audio + imagen:

- [`create(audio_path, image_path)`](src/modules/video_helper/video_creator.py:30) - Crea video MP4 combinando audio e imagen
- Genera archivo en `/tmp/videos/` con nombre UUID
- Escala imagen a 640x360 con padding para mantener aspecto
- Usa GPU (h264_nvenc) si está disponible, fallback a CPU
- Audio: AAC 96k, 48kHz, estéreo

### [`audio_routes.py`](src/modules/audio_routes.py)

Endpoints REST para procesamiento de audio:

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/audio/info` | POST | Obtener metadata del audio |
| `/audio/convert` | POST | Convertir audio (WAV/MP3) |
| `/audio/clean` | POST | Limpiar audio (normalizar, convertir) |
| `/audio/validate` | POST | Validar audio para transcripción |
| `/audio/validate-by-path` | POST | Validar audio por ruta de archivo |

**Endpoints detallados:**

#### `/audio/info`
Obtiene metadata del archivo de audio.

```bash
curl -X POST http://localhost:8080/audio/info \
  -F "file=@audio.mp3"
```

**Respuesta:**
```json
{
  "duration": 180.5,
  "codec": "mp3",
  "sample_rate": 44100,
  "channels": 2
}
```

#### `/audio/convert`
Convierte audio a formato especificado (WAV o MP3).

```bash
curl -X POST http://localhost:8080/audio/convert \
  -F "file=@audio.mp3" \
  -F "format=wav"
```

#### `/audio/clean`
Limpia el audio: normaliza volumen y convierte a formato estándar (WAV 16kHz mono).

```bash
curl -X POST http://localhost:8080/audio/clean \
  -F "file=@audio.mp3"
```

#### `/audio/validate`
Valida si un archivo de audio es aptopara transcripción. Analiza:
- Duración
- Frecuencia de muestreo
- Canales
- Bitrate
- Volumen (mean/max)
- Silencio detected
- Presencia de voz

```bash
curl -X POST http://localhost:8080/audio/validate \
  -F "file=@audio.mp3"
```

**Respuesta:**
```json
{
  "valid": true,
  "optimal": false,
  "issues": [],
  "warnings": ["Frecuencia baja, se recomienda 16kHz"],
  "recommendations": ["Convertir a 16kHz"],
  "metadata": {
    "duration_seconds": 120.5,
    "duration_formatted": "02:00",
    "codec": "mp3",
    "sample_rate_hz": 44100,
    "channels": 2,
    "bitrate_kbps": 192,
    "mean_volume_db": -18.5,
    "max_volume_db": -3.2,
    "silence_duration_seconds": 5.2,
    "silence_percentage": 4.3,
    "has_voice": true
  },
  "suggested_conversion": {
    "needs_conversion": true,
    "target_format": "wav",
    "target_sample_rate": 16000,
    "target_channels": 1,
    "command": "ffmpeg -i input.wav -ac 1 -ar 16000 output.wav"
  }
}
```

## Uso Práctico

### Flujo de optimización de video (asincrónico)

```bash
# 1. Iniciar optimización
curl -X POST http://localhost:8080/optimize \
  -H "Content-Type: application/json" \
  -d '{"input": "/videos/input.mp4", "output": "/videos/output.mp4"}'

# Respuesta: {"success": true, "process_id": "abc123", "message": "Optimización iniciada"}

# 2. Consultar estado ( polling )
curl http://localhost:8080/status/abc123

# Respuesta:
# {
#   "success": true,
#   "process_id": "abc123",
#   "status": "running",
#   "progress": 67.5,
#   "eta_seconds": 45,
#   "logs": [...]
# }

# 3. Cancelar si es necesario
curl -X POST http://localhost:8080/cancel/abc123

# 4. Listar procesos activos
curl http://localhost:8080/active
```

### Crear video desde audio e imagen

```bash
# Endpoint simple (síncrono - espera a que termine)
curl -X POST http://localhost:8080/create-from-audio \
  -H "Content-Type: application/json" \
  -d '{
    "audio_path": "/audios/podcast.mp3",
    "image_path": "/images/portada.jpg"
  }'

# Respuesta:
# {
#   "success": true,
#   "output_path": "/tmp/videos/video_x7y8z9.mp4",
#   "output_filename": "video_x7y8z9.mp4",
#   "image_used": "portada.jpg",
#   "audio_source": "podcast.mp3"
# }
```

### Verificar estado de GPU

```bash
curl http://localhost:8080/gpu-status

# Con GPU:
# {"success": true, "gpu_available": true, "gpu_name": "NVIDIA RTX 4090"}

# Sin GPU:
# {"success": true, "gpu_available": false}
```

### Script de ejemplo (Python)

```python
import requests
import time

BASE_URL = "http://localhost:8080"

# 1. Optimizar video
resp = requests.post(f"{BASE_URL}/optimize", json={
    "input": "/data/input.mp4",
    "output": "/data/output.mp4"
})
process_id = resp.json()["process_id"]

# 2. Polling hasta completar
while True:
    status = requests.get(f"{BASE_URL}/status/{process_id}").json()
    print(f"Progreso: {status['progress']}% - Estado: {status['status']}")
    
    if status["status"] in ["completed", "failed", "cancelled"]:
        break
    time.sleep(2)

if status["status"] == "completed":
    print(f"✅ Video optimizado: {status['output_file']}")
else:
    print(f"❌ Error: {status.get('error', 'Unknown')}")
```

## Instalación y Ejecución

### Requisitos previos

- Python 3.8+
- FFmpeg con soporte para NVENC (compilación con CUDA)
- NVIDIA GPU con drivers instalados (opcional pero recomendado)
- Docker (opcional)

### Uso Local

```bash
# Instalación de dependencias
pip install -r requirements.txt

# Ejecución
python app.py
```

El servicio estará disponible en `http://localhost:8080`

### Uso con Docker

```bash
# Build y ejecución
docker-compose up --build

# O por separado
docker build -t ffmpeg-cuda .
docker run -p 8080:8080 --gpus all ffmpeg-cuda
```

## Variables de Entorno

No se requieren variables de entorno obligatorias. La aplicación detecta automáticamente la GPU disponible.

## Licencia

MIT