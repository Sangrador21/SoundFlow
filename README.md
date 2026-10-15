# SoundFlow · Práctica 06 — Servicios web

Adaptación de la P04 a una API REST HTTP/HTTPS, con reproducción progresiva,
catálogos distribuidos y búsqueda por tiempo. Se mantiene Python, Tkinter,
pygame, el proceso independiente de audio, hilos para red y sincronización
con `RLock`, `Queue` y `Event`.

## Incorporar a tu repositorio

1. Dentro de tu copia de `SoundFlow`, confirma `git status`: rama `develop/p06`.
2. Copia **el contenido** de este paquete en la raíz del repositorio y reemplaza
   los archivos del mismo nombre. Conserva `.git/` y tus canciones de `music/`.
   El paquete incluye un tono original de prueba; no incluye tus MP3 anteriores.
3. Elimina el antiguo `soundflow/protocol.py`, que implementaba datagramas UDP
   y ya no se utiliza. Se incluye `README_P04.md` como referencia histórica.
4. Instala dependencias y prueba antes del commit. No reemplaces tu `.venv/`.
5. Después de probar: `git add .`, `git commit -m "Adapta P06 a servicios web y streaming"`
   y `git push`. Conserva la etiqueta `p04-base`. Al terminar la revisión
   podremos integrar a `main` y crear `p06-final`.

## Instalación — Mac / Linux

Python **3.10 o superior**, con Tkinter y salida de audio.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/check_environment.py
```

Si ya tienes `.venv`, basta activarlo e instalar `requirements.txt`.
Si tu distribución de Python en Mac no incluye Tkinter, usa una distribución
que lo incluya (por ejemplo el instalador de python.org). No se instala con pip.
FFmpeg se usa desde el sistema si está disponible; en caso contrario se toma
el ejecutable que instala `imageio-ffmpeg` mediante pip. No hace falta instalar
FFmpeg manualmente en las plataformas con rueda binaria disponible.

En Windows:

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python tools/check_environment.py
```

## Arranque rápido con tus canciones

Ejecuta cada comando en una terminal con el entorno activado y desde la raíz.
La carpeta `music/` se escanea directamente: MP3, WAV, OGG y FLAC.

Servidor 1:

```bash
python server.py --port 5000 --server-id S1 --music music --peer http://127.0.0.1:5001
```

Servidor 2 (puede usar otra carpeta con un catálogo distinto):

```bash
python server.py --port 5001 --server-id S2 --music music --peer http://127.0.0.1:5000
```

Cliente, en una tercera terminal:

```bash
python main.py --server http://127.0.0.1:5000 --fallback http://127.0.0.1:5001
```

Abre varias terminales para lanzar varios clientes. Cada cliente tiene su
propio proceso de audio y carpeta temporal; no comparten archivos descargados.

## Demostrar catálogos distintos

Se incluyen tonos originales de 12 segundos para probar sin música externa:

```bash
python tools/prepare_demo.py
```

Servidor 1:

```bash
python server.py --port 5000 --server-id S1 --music .demo_music/S1 --peer http://127.0.0.1:5001
```

Servidor 2:

```bash
python server.py --port 5001 --server-id S2 --music .demo_music/S2 --peer http://127.0.0.1:5000
```

S1 tiene `Exclusiva S1.wav` y `Compartida.wav`. S2 tiene `Exclusiva S2.wav`
y `Compartida.wav`. El cliente consulta cualquiera de los dos y ve **tres**
canciones únicas. La compartida se deduplica por SHA-256 del contenido, incluso
si su nombre cambia. Solicitar la exclusiva de S2 entrando por S1 demuestra
la coordinación entre servidores. Activa **Detalles de conexión** para ver
qué nodo entrega el audio y consulta las líneas `ASIGNACION` en la terminal.

Los scripts `run_server1_demo_*` y `run_server2_demo_*` preparan estos tonos y
arrancan cada nodo. `run_client_*` arranca el cliente con entrada S1 y respaldo S2.
Para usar tu música distribuida, crea por ejemplo `music/S1` y `music/S2`, coloca
archivos distintos en cada carpeta y utiliza esas rutas con `--music`.
No se escanean subcarpetas automáticamente.

## Interfaz y reproducción

- Seleccionar **una** canción en el catálogo inicia la reproducción directamente.
- Usa Ctrl/⌘ para seleccionar varias y **Agregar a cola**. La cola se despliega
  automáticamente; también puedes abrirla/cerrarla con el botón **Cola**.
- **A continuación** contiene las canciones pendientes, separadas de la actual.
  Al finalizar una pista continúa con la siguiente; al terminar la cola se detiene.
- Vaciar la cola no detiene la pista actual. Quitar canciones tampoco la interrumpe.
- Pausa, continúa, cambia de pista y ajusta volumen con los controles.
- Arrastra la barra de tiempo para adelantar o retroceder. Esto cancela la
  solicitud anterior y pide audio desde el segundo indicado. La búsqueda vuelve
  a iniciar la reproducción; no necesita esperar a descargar el archivo completo.
- El avance muestra tiempo musical absoluto, aunque la nueva transferencia
  comience en otro segundo. Los eventos tardíos de otra pista se descartan.
- Si la red es lenta se muestra buffering y se continúa cuando llegan muestras,
  sin confundir un EOF temporal del búfer con el final de la canción.

## Capacidad, redistribución y espera FIFO

Se retiraron `--max-streams` y el semáforo de ocho transferencias. **No hay un
máximo fijo de clientes ni de streams en la aplicación.** La máquina y su red
siguen teniendo recursos finitos.

Cada nodo reporta CPU y memoria con psutil. De forma predeterminada deja de
admitir una transferencia nueva si alguna alcanza 95%; se pueden ajustar
`--cpu-threshold` y `--memory-threshold`. Se cuentan sesiones para comparar
carga, nunca para rechazarlas por superar una cifra fija.

Para cada solicitud, el coordinador descubre los nodos conocidos, busca cuáles
poseen el identificador de la canción y elige el de menor carga que acepte audio.
El nodo elegido reserva la sesión atómicamente. Los pares también se descubren
mediante sus listas de conexiones, con un conjunto de URLs visitadas para evitar
ciclos. Basta una conexión entre componentes para descubrirlos cuando están vivos;
para tolerar fallos de nodos intermedios conviene configurar varios pares.

Si los poseedores están ocupados o hay nodos desconectados que podrían tener la
canción, la solicitud responde **202** y permanece en FIFO. El cliente consulta
su estado; se asigna cuando vuelve un nodo o se recuperan recursos. La espera
expira por defecto en 60 s (`--wait-timeout`); el cliente dispone de un presupuesto
de 90 s para adquisición/recuperación. El usuario puede detener o cambiar pista.
Si todos los nodos conocidos responden y ninguno tiene la canción, se devuelve
404 en lugar de una espera sin sentido.

La FIFO es global **por coordinador**, no una cola global compartida por todo
el clúster. Conserva el orden de llegada; una petición pendiente puede retrasar
las siguientes. La cola de la interfaz organiza pistas de ese usuario y es otra
estructura distinta.

### Prueba reproducible de espera sin inventar un máximo de streams

1. Arranca S1 normalmente y S2 con las carpetas demo y `--maintenance`.
2. Elige `Exclusiva S2` en el cliente que entra por S1.
3. Observa el mensaje de espera y la posición FIFO. S2 responde al catálogo,
   pero declara que temporalmente no acepta audio.
4. Cierra S2 con Ctrl+C y vuelve a iniciarlo sin `--maintenance`, antes de 60 s.
5. La solicitud pendiente se asigna y comienza a reproducir.

`--maintenance` es un estado explícito para esta demostración; no es un límite
oculto de transferencias. También puedes desconectar un nodo. El catálogo conserva
su última información en memoria si ya se había visto antes y muestra su ausencia.

## HTTPS local con verificación de certificado

Genera una CA de prueba y un certificado con nombres válidos para localhost:

```bash
python tools/create_cert.py
```

Servidor 1:

```bash
python server.py --port 5000 --server-id S1 --music .demo_music/S1 --peer https://127.0.0.1:5001 --cert certs/server.pem --key certs/server-key.pem --ca certs/ca.pem
```

Servidor 2:

```bash
python server.py --port 5001 --server-id S2 --music .demo_music/S2 --peer https://127.0.0.1:5000 --cert certs/server.pem --key certs/server-key.pem --ca certs/ca.pem
```

Cliente:

```bash
python main.py --server https://127.0.0.1:5000 --fallback https://127.0.0.1:5001 --ca certs/ca.pem
```

En otra computadora, agrega las IP de los nodos al generar el certificado:
`python tools/create_cert.py --host 192.168.1.10 --host 192.168.1.11`.
Usa `--host 0.0.0.0` para escuchar en LAN y `--base-url https://IP:PUERTO` para
anunciar cada servidor. Distribuye a los clientes **solo `ca.pem`** y copia a cada
servidor el certificado y clave de prueba correspondientes. Genera estos archivos
una sola vez para esta demostración local; regenerar la CA invalida la anterior.
`certs/` está ignorada por Git. La aplicación verifica certificados y hostnames;
no utiliza `verify=False`. En alojamiento público se empleará una CA pública.

## API REST

| Método y ruta | Función |
|---|---|
| `GET /api/health` | Estado del nodo, CPU, memoria y sesiones activas |
| `GET /api/node` | Catálogo local, pares y estado; no genera llamadas recursivas |
| `GET /api/catalog` | Unión de catálogos, nodos alcanzables y URLs sin conexión |
| `POST /api/requests` | Solicitar canción: `{"song_id":"ID_DEL_CATALOGO","start":12.5}` |
| `GET /api/requests/ID` | Estado `waiting`, `ready`, `failed` o `cancelled`, posición FIFO |
| `DELETE /api/requests/ID` | Cancelar petición y su sesión asignada |
| `POST /api/internal/streams` | Reserva local entre servidores; no redirige |
| `GET /api/streams/ID/audio` | Audio progresivo PCM de la sesión desde el segundo solicitado |
| `GET /api/streams/ID` | Estado de transferencia: reservada, transmitiendo, completada, etc. |
| `DELETE /api/streams/ID` | Cancelar decodificación/transferencia |

Códigos: 200 consulta, 201 asignación, 202 espera, 204 cancelación,
400 entrada inválida, 403 token interno inválido, 404 inexistente,
410 sesión usada/expirada, 503 nodo temporalmente ocupado y 504 espera agotada.
El POST devuelve `request_id`, `state`, `message`, `position` y, cuando está
listo, `stream` con URL, nodo e identificador del audio.

El audio se transmite como `application/octet-stream`, PCM S16LE, 44.1 kHz,
dos canales. Los encabezados `X-Audio-*`, `X-Sample-Rate` y `X-Channels`
describen el formato. No es una URL de MP3 directamente reproducible en el
navegador; el cliente Python interpreta ese audio. FFmpeg decodifica el archivo
original y aplica `-ss` para búsqueda por segundos. Se almacena localmente un
búfer PCM, se empieza al disponer de aproximadamente 1 s, y pygame reproduce
bloques cortos. TCP proporciona la entrega ordenada; no se conserva el ACK
manual ni Stop-and-Wait de UDP.

Si se interrumpe una transferencia, el cliente vuelve a buscar una asignación
y reanuda desde las muestras recibidas. Una reserva sin consumir expira en 30 s;
las sesiones terminadas y tickets antiguos se limpian periódicamente. La caché
de cada cliente se elimina al cerrar normalmente la aplicación.

## Pruebas automatizadas

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas del servicio abren nodos HTTP reales en puertos dinámicos, decodifican
audio y comprueban unión de catálogos, deduplicación, ausencia del máximo fijo,
FIFO, cancelación, errores, avance exacto, respaldo del cliente y HTTPS validado.
El proceso de reproducción se prueba con el controlador de audio `dummy` de SDL,
sin necesitar altavoces. Esto valida estados y tiempos, no la calidad auditiva.
Las pruebas gráficas requieren un entorno con pantalla; se documentan en
`VALIDACION.md` cuando están disponibles.

## Alcance y siguiente etapa

Esta entrega mantiene una **interfaz de escritorio** que consume servicios web.
Para publicar un frontend en GitHub Pages habría que crear un cliente web adicional.
La API puede prepararse después para Render, Google Cloud, Azure o AWS; aquí no
se crean cuentas ni se despliega.

El servidor integrado de Flask es para pruebas. Para un alojamiento público habrá
que configurar un servidor WSGI adecuado y TLS del proveedor. Por ahora el estado
se mantiene en memoria y se debe usar **un solo proceso WSGI por nodo** con hilos:
varios workers independientes no compartirían FIFO ni sesiones. La caída del
coordinador pierde sus tickets; el cliente puede utilizar un respaldo y solicitar
nueva asignación. No hay persistencia distribuida de tickets ni usuarios.

El formato PCM simplifica avance exacto y buffering en todos los formatos, pero
usa unos 176.4 KB/s de red y disco por pista y requiere un decodificador FFmpeg
por transferencia activa. La caché dura la sesión de cliente; reservar disco
suficiente es parte de la prueba. Un servicio comercial usaría códecs comprimidos,
segmentos/HLS y almacenamiento/CDN. Los umbrales de CPU/memoria no predicen todas
las formas de saturación, como congestión de red; los errores de transporte siguen
activando recuperación/espera.

Para pruebas en una red de confianza. Las sesiones son identificadores aleatorios,
pero no se implementa autenticación de usuarios. Puede protegerse la reserva entre
pares definiendo la misma variable `SOUNDFLOW_CLUSTER_TOKEN` en todos los nodos;
no se guarda ningún token en el código. Antes de exposición pública se revisarán
autenticación, restricciones de red y despliegue.

Base revisada: `Sangrador21/SoundFlow`, rama `develop/p06`, commit
`40ee67c52d116fe56807c06cf0b170d291796557` (P04 subida por el usuario).
