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
├── app.py                    # Punto de entrada principal
├── src/
│   └── modules/              # Módulos de la aplicación
│       ├── __init__.py       # Exports públicos
│       ├── config.py         # Configuración de Flask
│       ├── utils.py          # Utilidades generales
│       ├── gpu.py            # Detección de GPU y configuración
│       ├── process_manager.py # Gestión de procesos
│       ├── ffmpeg_runner.py  # Ejecutor de FFmpeg
│       ├── video_routes.py  # Endpoints de video
│       └── audio_routes.py   # Endpoints de audio
├── docker-compose.yml        #Orquestación Docker
├── Dockerfile               # Imagen del contenedor
└── requirements.txt          # Dependencias Python
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

**Ejemplo de uso - Optimizar video:**

```bash
curl -X POST http://localhost:8080/optimize \
  -H "Content-Type: application/json" \
  -d '{"input": "/path/to/video.mkv", "output": "/path/to/output.mkv"}'
```

**Parámetros de optimización:**
- Codec de video: `h264_nvenc` (NVIDIA Encoder)
- Preset: Automático según GPU detectada
- Bitrate: 1800k (variable)
- Audio: AAC 128k, 48kHz, estéreo

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

## Uso Local

```bash
# Instalación de dependencias
pip install -r requirements.txt

# Ejecución
python app.py
```

El servicio estará disponible en `http://localhost:8080`

## Uso con Docker

```bash
# Build y ejecución
docker-compose up --build

# O单独
docker build -t ffmpeg-cuda .
docker run -p 8080:8080 --gpus all ffmpeg-cuda
```

## Variables de Entorno

No se requieren variables de entorno obligatorias. La aplicación detecta automáticamente la GPU disponible.

## Licencia

MIT