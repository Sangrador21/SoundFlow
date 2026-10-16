# SoundFlow — P06: streaming mediante servicios web

SoundFlow es una aplicación web de música con múltiples clientes y servidores. El frontend utiliza **React, TypeScript, Vite y Tailwind CSS**; el backend conserva la API REST de Python y Flask, los catálogos distribuidos, la asignación por recursos y la espera FIFO.

## Aplicación desplegada

[Acceder a SoundFlow](https://sangrador21.github.io/SoundFlow/)

### Servidores de la API

- [Servidor S1](https://soundflow-s1.onrender.com/api/health)
- [Servidor S2](https://soundflow-s2.onrender.com/api/health)


## Funciones

- Reproducción directa desde la biblioteca, búsqueda y filtro por servidor.
- Selección múltiple y cola opcional; vaciarla no detiene la canción actual.
- Pausa, continuación, anterior, siguiente, detención, volumen y avance por segundos.
- Audio progresivo en un AudioWorklet independiente del renderizado de React.
- Recuperación de una transferencia desde la última muestra completa recibida, sin duplicar audio.
- Servidores con bibliotecas distintas y canciones compartidas deduplicadas por SHA-256.
- Asignación al nodo disponible de menor carga, con reservas sincronizadas.
- Sin un máximo fijo de clientes impuesto por la aplicación. La admisión depende de CPU y memoria.
- Espera FIFO por coordinador, cancelación y vencimiento de solicitudes.
- Vista de los servidores con métricas reales y configuración de las URL desde el navegador.
- HTTPS público mediante los certificados administrados por Render.

## Organización

| Ruta | Responsabilidad |
|---|---|
| `backend/server.py` | Servidor local por línea de comandos |
| `backend/wsgi.py` | Entrada WSGI para Gunicorn |
| `backend/soundflow/server_core.py` | Catálogos, descubrimiento, asignación, FIFO y transmisión |
| `backend/soundflow/config.py` | Variables de entorno y validación de configuración |
| `backend/soundflow/resources.py` | Métricas del host o cuotas de cgroup v2 |
| `backend/tests/` | Pruebas de API, concurrencia, certificados y configuración web |
| `frontend/src/app/` | Aplicación y proveedor del estado compartido |
| `frontend/src/components/` | Distribución general y componentes reutilizables |
| `frontend/src/features/catalog/` | Biblioteca, filtros y selección |
| `frontend/src/features/player/` | Controlador, motor de audio, reproductor y cola |
| `frontend/src/features/cluster/` | Estado y configuración de los servidores |
| `frontend/src/services/` | Cliente HTTP, asignación y consulta de tickets |
| `frontend/src/styles/` | Tema, estilos base y estilos por función |
| `frontend/public/worklets/` | Procesador PCM del hilo de audio |
| `deploy/catalogs/` | Manifiestos con las canciones de S1 y S2 |
| `tools/` | Preparación de bibliotecas y comprobaciones |
| `.github/workflows/` | Pruebas y publicación en GitHub Pages |

## Requisitos

- Python 3.12 recomendado para coincidir con el contenedor de despliegue.
- Node.js 24 y npm. Las dependencias exactas del frontend están en `package-lock.json`.
- Un navegador actualizado con AudioWorklet y Web Audio: Safari, Chrome, Edge o Firefox.
- FFmpeg; localmente se utiliza el del sistema o el de `imageio-ffmpeg`. La imagen Docker instala FFmpeg.

El backend ya no necesita Tkinter, pygame ni una salida de audio en el servidor.

## Instalación local

Desde la raíz del repositorio:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/check_environment.py
python tools/build_catalog.py
```

Si el entorno ya existe, solo actívalo. En Windows se activa con `.venv\Scripts\activate`; los ejemplos de continuación de línea `\` deben escribirse en una sola línea en CMD.

Los manifiestos utilizan las 18 canciones MP3 originales presentes en `music/`. El tono `demo_tono.wav` se conserva como recurso de prueba y queda fuera de los catálogos de música.

| Nodo | Biblioteca | Distribución |
|---|---|---|
| S1 | 12 canciones | 6 exclusivas y 6 compartidas |
| S2 | 12 canciones | 6 exclusivas y las mismas 6 compartidas |
| Catálogo agregado | 18 canciones únicas | Las compartidas aparecen una sola vez |

Compartidas: Beautiful Things, Can I Call You Tonight, Cleopatra, Daylight, On Melancholy Hill y Sweater Weather.

Exclusivas de S1: California Sand, Cerraron Chipinque, De Música Ligera, Don't Kill the Magic, End Of Beginning y Eres tú.

Exclusivas de S2: I Wanna Be Yours, Stubborn Love, Summertime Sadness, Te Veo a la Vuelta, Todo Lo Fue y Yo Todo Lo Doy.

`tools/build_catalog.py` copia exclusivamente los archivos de cada manifiesto a `.local_music/S1` y `.local_music/S2`. No altera los originales. Sincroniza únicamente los archivos que generó y rechaza una salida que contenga archivos ajenos. Estas copias no se suben a Git; Docker prepara la misma selección al construir cada servidor.

### Agregar canciones

1. Guarda el audio original en `music/` (MP3, WAV, OGG o FLAC).
2. Agrega su nombre exacto al JSON de S1, S2 o ambos dentro de `deploy/catalogs/`.
3. Ejecuta `python tools/build_catalog.py` y reinicia los nodos locales.
4. Actualiza la biblioteca en el navegador. No se necesita cambiar el frontend ni fijar un nuevo número de canciones en las pruebas.
5. Para publicar, sube el audio y los manifiestos; reconstruye los servicios de Render que cambien.

La prueba de integración calcula los identificadores SHA-256, los servidores de cada canción y el conteo de cada nodo leyendo los manifiestos y los audios originales. También se comprueba que todo audio original esté asignado (excepto el tono de prueba). Conserva al menos una canción compartida y una exclusiva por nodo para demostrar la distribución y el acceso a canciones remotas.

### Iniciar los servidores

En dos terminales con el entorno activo, desde la raíz:

**S1**

```bash
python backend/server.py --port 5000 --server-id S1 \
  --music .local_music/S1 --peer http://127.0.0.1:5001
```

**S2**

```bash
python backend/server.py --port 5001 --server-id S2 \
  --music .local_music/S2 --peer http://127.0.0.1:5000
```

### Iniciar el frontend

En otra terminal:

```bash
cd frontend
npm ci
npm run dev
```

Abre **http://localhost:5173**. En desarrollo se utilizan los servidores locales anteriores; puedes cambiarlos desde **Configurar servidores**. No es necesario crear archivos `.env` para esta prueba.

`localhost` es un contexto admitido para Web Audio. Al publicar, la página y las API deben utilizar HTTPS. Abrir la página desde una IP LAN con HTTP puede impedir AudioWorklet.

## Uso

Pulsa una canción o su botón de reproducción para escucharla directamente. Para preparar varias, marca sus casillas y usa **Agregar a cola**. El panel se abre al agregar canciones, se oculta cuando queda vacío y puede alternarse con **Cola**.

El reproductor inferior permite pausar, continuar, detener, cambiar de pista y ajustar el volumen. La barra de tiempo solicita audio desde la posición elegida; el avance realizado mientras está pausado conserva la pausa. La recepción de audio se mantiene progresiva, con un búfer de aproximadamente 20 segundos para evitar descargar toda la canción en memoria.

**Servidores** muestra la información de la última consulta al clúster. **Actualizar biblioteca** vuelve a consultar los nodos. Configurar nuevas direcciones detiene la reproducción y las guarda únicamente en ese navegador.

El audio comienza tras un gesto del usuario. Si el navegador suspende el contexto de audio, utiliza reproducir para continuar.

## Comunicación y coordinación

1. El navegador consulta `/api/catalog` y puede usar otra URL si una entrada falla.
2. Para reproducir, envía `song_id` y `start` a `/api/requests`.
3. El coordinador descubre los nodos conocidos, localiza los que tienen la canción y selecciona uno según sesiones, CPU y memoria.
4. El nodo elegido reserva la sesión. Si no puede asignarse todavía, el ticket permanece en FIFO y el cliente consulta su estado.
5. El navegador recibe PCM del nodo asignado; un AudioWorklet lo reproduce en un hilo de audio separado.
6. Si la transferencia se interrumpe, solicita otra asignación desde las muestras completas ya recibidas. Los bytes de una muestra incompleta se descartan y se vuelven a pedir.

La cola de canciones del usuario es distinta de la FIFO de solicitudes del servicio. La FIFO existe por coordinador y conserva el orden de llegada; una solicitud pendiente puede retrasar las siguientes.

Los umbrales de admisión son 95 % de CPU y memoria por defecto. La espera del servicio vence a los 120 segundos y se configura con `SOUNDFLOW_WAIT_TIMEOUT`. La recuperación del cliente también tiene un presupuesto finito. Una canción que no existe en los nodos conocidos genera un error, no una espera ilimitada.

## API REST

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/health` | Estado del nodo, carga y sesiones |
| GET | `/api/node` | Catálogo local y pares conocidos |
| GET | `/api/catalog` | Catálogo agregado y nodos disponibles o sin conexión |
| POST | `/api/requests` | Solicitar una canción desde un segundo |
| GET | `/api/requests/<id>` | Consultar asignación o posición FIFO |
| DELETE | `/api/requests/<id>` | Cancelar solicitud y sesión |
| POST | `/api/internal/streams` | Reserva interna entre servidores |
| GET | `/api/streams/<id>/audio` | Audio PCM progresivo |
| GET | `/api/streams/<id>` | Estado de la transferencia |
| DELETE | `/api/streams/<id>` | Cancelar transferencia |

El audio utiliza PCM S16LE, dos canales y 44.1 kHz. El servidor normaliza el audio y recorta por índice de muestra, para que una reanudación de MP3 coincida con la decodificación continua. Recorrer el audio previo a la posición elegida puede aumentar el tiempo de búsqueda en archivos largos. Los encabezados `X-Audio-Format`, `X-Sample-Rate`, `X-Channels`, `X-Audio-Start` y `X-Audio-Duration` describen la transferencia y están expuestos mediante CORS.

## Configuración del backend

Consulta `backend/.env.example`. Los valores pueden establecerse como variables del proceso o en `backend/.env` para uso local.

| Variable | Uso |
|---|---|
| `SOUNDFLOW_NODE_ID` | Identificador del nodo: S1 o S2 |
| `SOUNDFLOW_BASE_URL` | URL pública anunciada; en Render se usa automáticamente `RENDER_EXTERNAL_URL` si no se establece |
| `SOUNDFLOW_MUSIC_DIR` | Biblioteca local; en Docker se configura como `/app/music` |
| `SOUNDFLOW_PEERS` | URL base de los pares, separadas por comas |
| `SOUNDFLOW_CORS_ORIGINS` | Orígenes permitidos del frontend, sin rutas |
| `SOUNDFLOW_CLUSTER_TOKEN` | Token compartido solo entre servidores |
| `SOUNDFLOW_WAIT_TIMEOUT` | Vencimiento de espera, en segundos |
| `SOUNDFLOW_PEER_TIMEOUT` | Tiempo de espera para consultar pares |
| `SOUNDFLOW_CPU_THRESHOLD` | Umbral de CPU para admitir transferencias |
| `SOUNDFLOW_MEMORY_THRESHOLD` | Umbral de memoria para admitir transferencias |
| `SOUNDFLOW_MAINTENANCE` | `true` para consultar el catálogo sin admitir audio local |
| `PORT` | Puerto del servidor WSGI proporcionado por Render |

CORS permite orígenes explícitos. Para GitHub Pages, el origen es `https://sangrador21.github.io`, sin `/SoundFlow/`. El token del clúster nunca se coloca en variables `VITE_*`, en GitHub Pages ni en el código del navegador.

## Despliegue

La guía completa está en **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**:

- Dos servicios Docker en Render, uno por nodo.
- Cada imagen final contiene solo las canciones de su manifiesto.
- Gunicorn con un único worker y varios hilos, porque las sesiones y la FIFO están en memoria.
- Frontend estático en GitHub Pages, compilado mediante GitHub Actions con base `/SoundFlow/`.
- URL públicas de las API configuradas mediante la variable de repositorio `SOUNDFLOW_API_URLS`.
- Certificados HTTPS administrados por las plataformas; no se suben los certificados locales.

## Pruebas

```bash
python -m pytest -q
cd frontend
npm test
npm run build
```

Para verificar el cliente TypeScript contra dos procesos Gunicorn reales, vuelve a la raíz y ejecuta en macOS o Linux:

```bash
python tools/check_web_integration.py
```

Esta prueba prepara las bibliotecas, inicia ambos nodos en puertos locales temporales, compara el catálogo real completo con los manifiestos, comprueba la deduplicación y recibe una canción de S2 entrando por S1 con una URL de respaldo. Después cierra los procesos. El test de integración se omite en `npm test` normal porque necesita esos procesos.

Las pruebas unitarias cubren la concurrencia, FIFO, cancelación, avance, CORS, certificados, límites de recursos, controles de la interfaz y recuperación PCM sin duplicados. El procesador del AudioWorklet se prueba con muestras de audio y el DOM se prueba con jsdom. La salida física de audio y el comportamiento visual deben verificarse también en un navegador real.

GitHub Actions ejecuta las pruebas y la compilación; además construye las imágenes Docker de ambos nodos.

## Alcance

La práctica conserva el estado de solicitudes y sesiones en memoria. Reiniciar un nodo pierde ese estado; el cliente puede buscar una nueva asignación. No se configura Gunicorn con múltiples workers ni se utiliza `--preload`.

El PCM utiliza aproximadamente 176.4 kB/s por transferencia y requiere decodificación con FFmpeg. Los recursos físicos y los hilos disponibles del servidor siguen siendo finitos, aunque la aplicación no imponga un contador máximo de clientes.

Los servicios gratuitos de Render pueden entrar en reposo y perder cambios realizados en su disco local. Las canciones se incorporan a la imagen durante la construcción; no dependen de archivos subidos durante la ejecución. Esta versión no incorpora cuentas de usuario ni autenticación del oyente.
