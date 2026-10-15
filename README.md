# SoundFlow — Práctica 06: servicios web

SoundFlow es una aplicación de streaming de música con múltiples clientes y servidores. Esta práctica adapta la base de la práctica 04 a una API REST mediante HTTP y HTTPS, conservando una interfaz de escritorio desarrollada con Python y Tkinter.

Cada servidor puede almacenar un catálogo diferente. El cliente consulta el catálogo del conjunto de servidores y solicita el audio al nodo que tiene la canción y dispone de recursos para atenderla.

## Funcionalidades

- Catálogo distribuido con búsqueda por canción o artista.
- Identificación de canciones por SHA-256 del contenido para evitar duplicados entre servidores.
- Reproducción directa al seleccionar una canción.
- Cola de reproducción opcional, separada de la canción actual.
- Pausa, continuación, anterior, siguiente, detención y volumen.
- Avance y retroceso a un segundo específico de la canción.
- Recepción progresiva del audio y recuperación ante interrupciones de transferencia.
- Servidor de entrada alternativo mediante `--fallback`.
- Espera FIFO cuando no es posible asignar una solicitud de inmediato.
- HTTPS con validación del certificado y del nombre del servidor.
- Interfaz con paleta morada, controles con iconos y detalles de conexión opcionales.

## Tecnologías

| Componente | Tecnología |
|---|---|
| Interfaz de escritorio | Tkinter y ttk |
| API REST | Flask |
| Cliente HTTP y comunicación entre servidores | Requests |
| Reproducción | pygame.mixer en un proceso independiente |
| Decodificación y búsqueda temporal | FFmpeg |
| Metadatos musicales | Mutagen |
| Monitoreo de CPU y memoria | psutil |
| Certificados de prueba | cryptography |
| Pruebas automatizadas | pytest |

Las peticiones de red se ejecutan en hilos. La interfaz y el proceso de audio intercambian comandos y eventos mediante colas de `multiprocessing`. Los servidores sincronizan las reservas, sesiones y solicitudes pendientes para atender peticiones concurrentes.

## Requisitos e instalación

Se requiere Python 3.10 o superior, Tkinter y una salida de audio. Las dependencias deben estar instaladas en un entorno virtual del proyecto.

```bash
git clone https://github.com/Sangrador21/SoundFlow.git
cd SoundFlow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/check_environment.py
```

En Windows, crea y activa el entorno con:

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python tools/check_environment.py
```

FFmpeg se obtiene del sistema si está disponible. En caso contrario, la aplicación utiliza el ejecutable de `imageio-ffmpeg` cuando existe una distribución binaria compatible con la plataforma.

### Entorno de macOS

Tkinter debe estar disponible en la instalación de Python; no se instala mediante pip. Para Python 3.14 instalado con Homebrew, el componente correspondiente es:

```bash
brew install python-tk@3.14
```

Si pygame está instalado pero falta `pygame.mixer`, instala las dependencias de audio y recompila pygame dentro del entorno virtual:

```bash
brew install sdl2_mixer pkgconf
python -m pip install --no-cache-dir --force-reinstall --no-binary=pygame pygame==2.6.1
```

Comprueba el audio con:

```bash
python -c "import pygame.mixer; pygame.mixer.init(); print('Audio OK:', pygame.mixer.get_init()); pygame.mixer.quit()"
```

## Bibliotecas de música

Desde la raíz del proyecto, crea una carpeta para cada servidor:

```bash
mkdir -p music/S1 music/S2
```

Coloca archivos diferentes en cada una. Puedes copiar una misma canción a ambas para comprobar que aparece una sola vez en el catálogo agregado.

Se admiten archivos MP3, WAV, OGG y FLAC. Cada servidor lee los archivos directamente dentro de la carpeta indicada por `--music`; no recorre subcarpetas.

Las carpetas locales `music/S1/` y `music/S2/` están ignoradas por Git. Al clonar el proyecto en otra computadora deben crearse y poblarse nuevamente.

### Música de prueba opcional

Para probar sin preparar archivos musicales, ejecuta:

```bash
python tools/prepare_demo.py
```

Se generan dos bibliotecas en `.demo_music/S1` y `.demo_music/S2`, con tonos WAV de 12 segundos: una pista exclusiva de cada servidor y otra compartida. Para utilizarlas, sustituye las rutas `music/S1` y `music/S2` de los comandos de arranque por `.demo_music/S1` y `.demo_music/S2`.

## Ejecución mediante HTTP

Ejecuta cada componente en una terminal distinta, desde la raíz del proyecto y con el entorno virtual activo.

**Servidor S1:**

```bash
python server.py --port 5000 --server-id S1 \
  --music music/S1 --peer http://127.0.0.1:5001
```

**Servidor S2:**

```bash
python server.py --port 5001 --server-id S2 \
  --music music/S2 --peer http://127.0.0.1:5000
```

**Cliente:**

```bash
python main.py --server http://127.0.0.1:5000 \
  --fallback http://127.0.0.1:5001
```

Para probar varios clientes, ejecuta el comando del cliente en terminales adicionales. Cada instancia utiliza su propio proceso de audio y caché temporal.

Los ejemplos con `\` utilizan continuación de línea de Bash/zsh. En CMD de Windows, escribe cada comando completo en una sola línea.

## Ejecución mediante HTTPS

Detén los servidores HTTP antes de reutilizar sus puertos. Genera una vez la CA local y el certificado de los servidores:

```bash
python tools/create_cert.py
```

Se crean `certs/ca.pem`, `certs/server.pem` y `certs/server-key.pem`, válidos para pruebas con `localhost` y `127.0.0.1`. El generador no sobrescribe certificados existentes. Si ya están generados y son válidos, reutilízalos.

**Servidor S1:**

```bash
python server.py --port 5000 --server-id S1 \
  --music music/S1 --peer https://127.0.0.1:5001 \
  --cert certs/server.pem --key certs/server-key.pem --ca certs/ca.pem
```

**Servidor S2:**

```bash
python server.py --port 5001 --server-id S2 \
  --music music/S2 --peer https://127.0.0.1:5000 \
  --cert certs/server.pem --key certs/server-key.pem --ca certs/ca.pem
```

**Cliente:**

```bash
python main.py --server https://127.0.0.1:5000 \
  --fallback https://127.0.0.1:5001 --ca certs/ca.pem
```

El cliente y los servidores verifican los certificados usando `--ca`. Los certificados incorporan identificadores de clave y extensiones compatibles con la validación X.509 estricta.

Para probar en una red local con otras computadoras, incluye sus IP o nombres al generar el certificado mediante `--host`. En cada servidor, utiliza `--host 0.0.0.0`, anuncia su dirección accesible con `--base-url https://IP:PUERTO` y configura los pares con sus direcciones reales. Los clientes necesitan la CA pública `ca.pem`; la clave privada debe permanecer en los servidores de prueba. Las direcciones anunciadas deben coincidir con los nombres o IP incluidos en el certificado.

## Uso del cliente

Selecciona una canción en la biblioteca para reproducirla. Para preparar varias pistas, selecciónalas con Ctrl/⌘ y utiliza **Agregar a cola**. El panel **A continuación** se abre al agregar canciones y se oculta cuando queda vacío; también puede abrirse o cerrarse mediante **Cola**.

Los controles con iconos permiten cambiar de pista, reproducir o pausar y detener. Su descripción aparece al pasar el cursor; pueden activarse con el teclado. Arrastra la barra de tiempo para adelantar o retroceder: el cliente cancela la transferencia anterior y solicita audio desde la posición elegida.

Vaciar la cola no detiene la canción actual. Al terminar una pista se reproduce la siguiente de la cola; si no quedan canciones, la reproducción finaliza. **Detalles de conexión** muestra el servidor de entrada y el nodo que entrega el audio.

## Asignación de solicitudes y espera

El servidor que recibe una petición descubre los nodos conocidos y localiza los que tienen la canción. La asignación considera las sesiones activas, la CPU y la memoria; el nodo elegido reserva la sesión de forma sincronizada.

No existe un límite fijo de transferencias por número de clientes. La admisión depende de los recursos: por defecto, un nodo deja de aceptar nuevas transferencias si su CPU o memoria alcanza el 95 %. Los umbrales pueden ajustarse mediante `--cpu-threshold` y `--memory-threshold`.

Cuando no hay un nodo disponible que pueda proporcionar la canción, la solicitud puede permanecer en espera FIFO. El cliente consulta su estado y continúa cuando se asigna un servidor. La espera del coordinador vence después de 60 segundos por defecto; se configura con `--wait-timeout`. Si todos los nodos conocidos responden y ninguno tiene la canción, se informa que no existe.

La FIFO pertenece a cada coordinador; no es una cola global compartida por todo el clúster. Esta espera del servicio es independiente de la cola de canciones del usuario.

### Prueba de espera y recuperación

1. Inicia S1 normalmente y S2 agregando `--maintenance` al comando de arranque.
2. Desde el cliente conectado a S1, solicita una canción que solo esté en S2.
3. Observa el estado de espera y su posición FIFO.
4. Detén S2 y reinícialo sin `--maintenance`, antes de que venza la espera.
5. Comprueba que la solicitud se asigna y comienza la reproducción.

`--maintenance` mantiene disponible el catálogo del nodo, pero desactiva temporalmente la admisión de audio local.

## API REST

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/health` | Estado, carga y sesiones del nodo |
| GET | `/api/node` | Catálogo local y pares conocidos |
| GET | `/api/catalog` | Catálogo agregado de los servidores |
| POST | `/api/requests` | Solicitar una canción y una posición inicial |
| GET | `/api/requests/<id>` | Consultar la asignación o espera |
| DELETE | `/api/requests/<id>` | Cancelar una solicitud y su sesión |
| POST | `/api/internal/streams` | Reservar audio local entre servidores |
| GET | `/api/streams/<id>/audio` | Recibir el audio de la sesión |
| GET | `/api/streams/<id>` | Consultar el estado de una transferencia |
| DELETE | `/api/streams/<id>` | Cancelar una transferencia |

Ejemplo del cuerpo JSON para solicitar audio:

```json
{
  "song_id": "IDENTIFICADOR_OBTENIDO_DEL_CATALOGO",
  "start": 30.0
}
```

Una solicitud asignada responde con `201`; una pendiente, con `202`. El audio se transmite como PCM S16LE, estéreo, a 44.1 kHz. FFmpeg decodifica el archivo original y aplica la posición de inicio solicitada. El cliente comienza a reproducir al disponer de aproximadamente un segundo de audio y continúa recibiendo datos en segundo plano.

## Estructura del proyecto

| Archivo o carpeta | Contenido |
|---|---|
| `main.py` | Punto de entrada del cliente |
| `server.py` | Punto de entrada del servidor REST |
| `soundflow/` | Interfaz, componentes visuales, cliente HTTP, audio y lógica del servidor |
| `music/` | Archivos musicales y bibliotecas locales |
| `tools/` | Comprobación del entorno, certificados y tonos de prueba |
| `tests/` | Pruebas automatizadas |
| `requirements.txt` | Dependencias de ejecución |
| `requirements-dev.txt` | Dependencias para ejecutar pruebas |
| `pytest.ini` | Configuración de pytest |
| `.gitignore` | Exclusiones de archivos locales y temporales |

## Pruebas

Con el entorno virtual activo:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas cubren catálogos distribuidos, deduplicación, coordinación entre servidores, concurrencia, espera FIFO, cancelación, recuperación de transferencias, búsqueda temporal, reproducción progresiva y certificados HTTPS con validación estricta. También verifican las acciones principales del controlador de la interfaz y la detección de dependencias de audio faltantes.

Las pruebas del reproductor utilizan una salida de audio de prueba de SDL. La revisión visual de Tkinter y la salida física de audio se comprueban ejecutando la aplicación en el equipo del usuario.

## Archivos locales y control de versiones

El entorno virtual, la caché de reproducción, los certificados locales, los tonos generados y las carpetas `music/S1/` y `music/S2/` están excluidos mediante `.gitignore`. Estos archivos se crean o configuran en cada instalación.

`main` contiene la versión estable y `develop/p06` se utiliza para el desarrollo de esta práctica. La etiqueta `p04-base` conserva la base original y `p06-final` identifica la versión de cierre de la práctica 06.

## Alcance

El cliente actual es una aplicación de escritorio que consume servicios web. Publicar una interfaz en GitHub Pages requeriría un cliente web adicional.

Los servidores incluidos se ejecutan con Flask para pruebas locales. La cola y las sesiones se mantienen en memoria; un reinicio pierde ese estado. Un despliegue posterior debe utilizar un servidor de producción y conservar un solo proceso con hilos por nodo mientras ese estado siga en memoria.

La transmisión PCM utiliza aproximadamente 176.4 kB/s por canción, además del búfer en disco y la decodificación con FFmpeg. No tener un límite fijo de clientes no elimina los límites físicos de CPU, memoria, disco y red.

La práctica no implementa autenticación de usuarios ni almacenamiento distribuido persistente. Puede protegerse la reserva interna de sesiones configurando el mismo `SOUNDFLOW_CLUSTER_TOKEN` en todos los servidores. El despliegue en nube queda como una etapa posterior.
