# SoundFlow P4 — Múltiples clientes / múltiples servidores

Esta versión parte directamente de SoundFlow P3. Se conservan el cliente gráfico, el proceso independiente de reproducción, el receptor UDP, Stop-and-Wait, ACK por fragmento, `RLock`, `Lock`, `Queue`, `Event` y el modelo `thread-per-stream`.

## Qué cambia en P4

- Cada servidor tiene una **capacidad local** (`--max-streams`). Ya no representa un máximo global de clientes.
- Si un servidor está lleno, envía un **sondeo de capacidad** a sus servidores pares (`cluster_capacity_request`). En ese momento el servidor actúa temporalmente como solicitante de recursos frente a otros servidores.
- Los pares responden con su carga, capacidad, cola y disponibilidad de la canción.
- Se aplica **Least-Loaded**: se elige el servidor con menor porcentaje de utilización; en empate, el de menor cola y menor número de streams activos.
- El cliente recibe una **redirección controlada** y conserva el mismo socket UDP.
- Cada solicitud tiene un `request_id` y una lista de servidores visitados para evitar ciclos S1 → S2 → S1.
- Si no existe capacidad inmediata en ningún servidor, la solicitud entra en una **cola FIFO**. Un hilo `queue-dispatcher` la atiende cuando se libera capacidad o cuando otro servidor queda disponible.
- Cada sesión sigue asociada a la dirección `(IP, puerto UDP)` del cliente y tiene su propia cola de ACK.

## Prueba local con dos servidores

Abra dos terminales dentro de la carpeta del proyecto.

Servidor 1:

```bash
python server.py --port 5000 --server-id S1 --advertise-host 127.0.0.1 --max-streams 2 --peer 127.0.0.1:5001
```

Servidor 2:

```bash
python server.py --port 5001 --server-id S2 --advertise-host 127.0.0.1 --max-streams 2 --peer 127.0.0.1:5000
```

Después pueden abrirse tantos clientes como se desee para la prueba:

```bash
python main.py --host 127.0.0.1 --port 5000
```

Todos pueden entrar por S1. Cuando S1 alcance su capacidad local, consultará a S2 y redirigirá nuevas solicitudes. Si ambos están ocupados, las solicitudes quedan en FIFO hasta que exista capacidad.

Para hacer visible el balanceo durante la demostración conviene usar `--max-streams 1` o `--max-streams 2` en cada servidor.

## Tres o más servidores

Cada servidor debe conocer a los demás con varios `--peer`. Ejemplo para S1:

```bash
python server.py --port 5000 --server-id S1 --advertise-host 127.0.0.1 --max-streams 2 --peer 127.0.0.1:5001 --peer 127.0.0.1:5002

python server.py --port 5001 --server-id S2 --advertise-host 127.0.0.1 --max-streams 2 --peer 127.0.0.1:5000 --peer 127.0.0.1:5002

python server.py --port 5002 --server-id S3 --advertise-host 127.0.0.1 --max-streams 2 --peer 127.0.0.1:5000 --peer 127.0.0.1:5001
```

Configure S2 y S3 de la misma forma, cambiando puerto, identificador y lista de pares.

## Prueba en varias computadoras

Use la IP LAN real en `--advertise-host` y en `--peer`. Ejemplo, si S1 está en `192.168.1.10` y S2 en `192.168.1.11`:

```bash
# S1
python server.py --host 0.0.0.0 --port 5000 --server-id S1 \
  --advertise-host 192.168.1.10 --peer 192.168.1.11:5000

# S2
python server.py --host 0.0.0.0 --port 5000 --server-id S2 \
  --advertise-host 192.168.1.11 --peer 192.168.1.10:5000
```

El cliente sólo necesita conocer un servidor de entrada:

```bash
python main.py --host 192.168.1.10 --port 5000
```

Los archivos de música deben estar disponibles en los servidores que puedan atender la solicitud. Para esta práctica lo más sencillo es mantener la misma carpeta `music/` en cada servidor.
