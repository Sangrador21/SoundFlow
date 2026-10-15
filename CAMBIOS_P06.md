# Cambios de P04 a P06

- `server.py`: servidor REST con URLs de pares, HTTP/HTTPS, carga/memoria y mantenimiento.
- `soundflow/server_core.py`: catálogo distribuido, reserva atómica, estados por solicitud,
  espera FIFO por coordinador, cancelación y respuesta progresiva FFmpeg.
- `soundflow/network_client.py`: peticiones HTTP en hilos, consultas de espera, respaldo,
  descarga PCM progresiva y recuperación desde las muestras recibidas.
- `soundflow/player_process.py`: proceso pygame que consume bloques PCM, distingue
  buffering de final real y descarta comandos de pistas anteriores.
- `soundflow/app.py`: reproducción desde catálogo, cola desplegable, búsqueda temporal,
  controles y detalles de conexión opcionales.
- `soundflow/library.py` y `models.py`: identificadores por contenido, metadatos y fuentes.
- Nuevos `audio.py` y `http_utils.py`: formato común y validación de URLs.
- `main.py`: cliente con URL, respaldo, CA y caché independiente por instancia.
- Scripts Mac/Linux y Windows actualizados; no quedan parámetros UDP ni max-streams.
- Herramientas para preparar dos bibliotecas de prueba, generar certificados y revisar entorno.
- Dependencias, pruebas e instrucciones completas.

Archivo retirado: `soundflow/protocol.py` (paquetes/ACK UDP). Elimínalo de tu
copia local al incorporar la actualización. `.git/`, la música existente y
el entorno virtual deben conservarse. La base P04 permanece en `p04-base`.

No se modificó ni se subió ningún archivo a tu repositorio remoto durante
esta implementación. El paquete se entrega para que lo incorpores y pruebes.
