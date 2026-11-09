# SoundFlow — P08: microservicios

Aplicación PWA de música con múltiples clientes y bibliotecas distribuidas. La P08 separa el catálogo, la asignación y los medios de la P07 en aplicaciones independientes comunicadas mediante REST/JSON. El audio conserva su transmisión binaria.

## Arquitectura

| Servicio | Responsabilidad | Puerto local |
|---|---|---|
| Gateway | Entrada pública para consultas y solicitudes | 8000 |
| Catálogo | Metadatos agregados, deduplicación y disponibilidad | 8001 |
| Reproducción | Tickets, FIFO, asignación y cancelación; SQLite privada | 8002 |
| Medios S1 | Biblioteca propia, sesiones, PCM y descargas MP3 | 5000 |
| Medios S2 | Segunda biblioteca y sesiones independientes | 5001 |

Cuatro capacidades en cinco procesos, con un contenedor por proceso. Los servicios de control se comunican por HTTP y no comparten bases de datos. La PWA solicita al gateway y recibe el audio directamente del medio asignado. [Arquitectura y contratos](docs/MICROSERVICES.md).

## Ejecución local

Requisitos: Python 3.12, Node.js 24/npm y un navegador actualizado. Se utiliza FFmpeg del sistema o el paquete imageio-ffmpeg. Docker es opcional.

Desde la raíz, crea el entorno si todavía no existe:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/run_microservices.py
```

Si ya tienes un entorno, actívalo y actualiza dependencias. Detén previamente los servidores P07. El lanzador prepara las bibliotecas, inicia los cinco procesos, genera un token local temporal y los detiene con Ctrl+C.

En otra terminal, desde la raíz:

```bash
cd frontend
npm ci
npm run dev
```

Abre `http://localhost:5173`. El gateway de desarrollo es `http://127.0.0.1:8000`. Configura esa dirección si la cambiaste; no introduzcas los medios como entrada de control.

## Compilación PWA

Con los microservicios activos, detén el frontend de desarrollo y ejecuta:

```bash
cd frontend
VITE_API_URLS="http://127.0.0.1:8000" VITE_BASE_PATH="/SoundFlow/" npm run build
npm run preview:pwa
```

Abre `http://localhost:5173/SoundFlow/`. El service worker se registra en la compilación, no en desarrollo. Las actualizaciones esperan una acción del usuario. [Guía PWA](docs/PWA.md).

## Funciones conservadas

- Reproducción desde biblioteca; búsqueda, filtro, selección y cola opcional.
- Pausa, volumen, anterior/siguiente, detención y avance por segundos.
- AudioWorklet, PCM S16LE estéreo a 44.1 kHz y recuperación por muestras completas.
- Hasta tres canciones recientes completas en IndexedDB, 24 MiB máximo por archivo, validación de tamaño/SHA-256 y eliminación de copias.
- Apertura de la interfaz sin conexión y biblioteca de referencia; reconexión para consultar el catálogo.
- Asignación según sesiones, CPU y memoria, sin un contador fijo de clientes. FIFO con cancelación y vencimiento.

## Música y distribución

Los originales están en `music/`; los manifiestos en `deploy/catalogs/S1.json` y `S2.json`. Hay 18 MP3 únicos, 12 por nodo y seis compartidos. El tono de demostración no forma parte de los catálogos. Para agregar canciones, añade el original y su nombre al manifiesto de uno o ambos nodos, ejecuta `python tools/build_catalog.py` y reinicia los medios. No hay un límite de cinco canciones ni es necesario modificar el frontend.

`.local_music/` contiene las copias generadas y permanece fuera de Git. Las imágenes de medios incluyen solo la selección de su manifiesto.

## Docker y publicación

`compose.yaml` inicia los cinco servicios. Configura el token en `.env` siguiendo `deploy/p08.env.example` y ejecuta `docker compose up --build -d`. El volumen playback-state conserva la SQLite privada. Consulta [MICROSERVICES.md](docs/MICROSERVICES.md) para comandos y pruebas de fallos.

La publicación P08 utiliza **`deploy/render.p08.yaml`** y requiere desplegar gateway, catálogo, reproducción y los dos medios. La PWA de Pages apunta únicamente al gateway. [Guía de publicación P08](docs/DEPLOYMENT_P08.md).

La dirección de la aplicación es [SoundFlow](https://sangrador21.github.io/SoundFlow/); la versión pública depende de la última publicación validada. El `render.yaml` y Dockerfile de raíz mantienen la publicación P07 hasta completar la migración. No se modifican servicios externos al aplicar el ZIP.

## Pruebas

```bash
python -m pytest -q
cd frontend
npm test
npm run build
cd ..
python tools/check_microservices.py
cd frontend
npx playwright install chromium
npm run test:pwa
```

Las pruebas incluyen contratos entre cinco servicios HTTP, caída de un medio o del catálogo, reservas idempotentes, FIFO, doce sesiones simultáneas, persistencia de tickets, descarga íntegra y controles de la PWA. La integración inicia cinco procesos Gunicorn y usa los audios reales. Checks construye las cinco imágenes además de ejecutar pruebas y compilación.

## Organización

| Ruta | Contenido |
|---|---|
| backend/microservices/ | Aplicaciones separadas, transporte y estado privado de reproducción |
| backend/service.py | Entrada local de un servicio P08 |
| backend/tests/test_microservices.py | Contratos y fallos por HTTP |
| frontend/src/features/ | Biblioteca, reproductor, copias locales y servidores |
| frontend/pwa/ | Generación del manifiesto y service worker |
| deploy/docker/ | Dockerfile por capacidad |
| deploy/render.p08.yaml | Blueprint de los cinco procesos P08 |
| tools/run_microservices.py | Arranque local sin Docker |
| tools/check_microservices.py | Integración de cinco procesos Gunicorn con el cliente real |

## Alcance

La entrega usa una instancia de reproducción y un worker Gunicorn por servicio. No incorpora alta disponibilidad ni escalado horizontal de las sesiones. Las sesiones de medios se pierden al reiniciarlos; el cliente solicita otra asignación o utiliza una copia local disponible. SQLite recupera tickets al reiniciar el proceso con el mismo archivo, pero el disco de Render Free es efímero y puede perderlo en redeploys o reinicios. Los límites físicos de CPU, memoria, hilos y almacenamiento siguen existiendo.

Los módulos P06/P07 se conservan para compatibilidad y pruebas de regresión; no son el arranque ni se incluyen en las imágenes de P08. No se agregaron cuentas de usuario, autenticación del oyente ni infraestructura de mensajería.
