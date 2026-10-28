# SoundFlow P07: aplicación web progresiva

La PWA utiliza la API REST/JSON de P06 sin modificar sus contratos, catálogos distribuidos, coordinación FIFO, reservas ni audio PCM. JSON corresponde a metadatos y operaciones; el audio sigue siendo binario. No había XML que convertir.

## Organización

| Archivo | Responsabilidad |
|---|---|
| `frontend/pwa/build.ts` | Generar manifiesto y worker desde la compilación real |
| `frontend/pwa/service-worker.js` | Instalación, activación, caché y exclusiones de red |
| `frontend/src/pwa/service-worker.ts` | Registro, detección y activación solicitada de versiones |
| `frontend/src/pwa/PwaPanel.tsx` | Instalación, instrucciones, actualización y desconexión |
| `frontend/src/pwa/network.ts` | Eventos de conexión del navegador |
| `frontend/src/features/catalog/catalog-storage.ts` | Biblioteca de referencia asociada a las URL configuradas |
| `frontend/public/icons/` | Iconos PNG, maskable y Apple basados en el símbolo existente |
| `frontend/e2e/` | Pruebas Chromium de la compilación bajo `/SoundFlow/` |

## Ciclo de vida y caché

- Se registra solo en una compilación, desde HTTPS o localhost; no se registra un worker nuevo en `npm run dev`.
- La URL es `BASE_URL + sw.js` y el ámbito es `BASE_URL`. En GitHub Pages corresponde a `/SoundFlow/`, igual que `id`, `start_url` y `scope` del manifiesto.
- El manifiesto declara apertura `standalone`, nombre, colores e iconos. La instalación depende del navegador y el dispositivo.
- La versión se obtiene mediante un hash del worker, la ruta base y el contenido final. La precarga incluye HTML, JS, CSS, fuentes, iconos y AudioWorklet.
- Si algún recurso falla, la instalación elimina su caché incompleta y no sustituye al worker anterior.
- Se sirve la interfaz de la versión instalada para evitar mezclar HTML nuevo con JS anterior.
- Una versión nueva espera. **Actualizar ahora** detiene la reproducción y recarga esa ventana; el aviso informa que su cola se pierde. No hay recarga automática al detectar la actualización.
- La activación elimina solo cachés anteriores con el prefijo de esta aplicación cuando no hay otras ventanas de SoundFlow que puedan necesitarlas. Si hay varias, conserva sus recursos hasta una posterior activación con una sola ventana. Nunca borra cachés de otros proyectos.
- Se comprueban actualizaciones al volver a la ventana, recuperar conexión y periódicamente mientras está visible.

## Exclusiones

Las URL de otros orígenes, rutas `/api/`, operaciones POST/DELETE, solicitudes Range y recursos multimedia se dejan a la red. Se precarga solo una lista conocida de archivos estáticos; no se almacenan respuestas desconocidas dinámicamente. No se guarda PCM, tickets, asignaciones ni métricas en Cache Storage.

El token del clúster sigue solo en los servidores; no aparece en el manifiesto, el worker ni las variables `VITE_*`.

## Sin conexión y canciones recientes

Después de una visita conectada que prepare el worker, la interfaz abre sin Internet. La última biblioteca de metadatos se identifica como referencia, sin inventar disponibilidad de los servidores.

Además, **Disponibles sin conexión** conserva hasta tres archivos MP3 completos en IndexedDB, separados de Cache Storage. El guardado automático comienza después de 1.5 segundos de reproducción desde un servidor. Solo hay una copia pendiente por ventana; cambiar de canción, detener, desconectar o desactivar el guardado cancela la descarga pendiente.

La descarga obtiene otra reserva normal mediante `/api/requests` desde cero, respetando descubrimiento, selección por recursos y FIFO. Después solicita `/api/streams/<id>/download` al nodo asignado. Los MP3 se conservan sin recodificar; WAV, OGG y FLAC se convierten a MP3 de 128 kb/s. El servidor comunica tamaño y SHA-256. El cliente verifica bytes, estado final y digest antes de confirmar una escritura atómica. Una transferencia incompleta, corrupta o cancelada no reemplaza las copias anteriores.

El máximo es tres canciones y 24 MiB por archivo. Al confirmar una cuarta, se elimina la menos recientemente utilizada. Escuchar una copia local también actualiza su fecha de uso. Las transacciones de IndexedDB serializan escrituras entre ventanas y BroadcastChannel actualiza sus listas. Si no hay espacio o IndexedDB está bloqueado, se informa el error sin detener el streaming normal.

Las canciones completas tienen botones de reproducción y eliminación. También pueden reproducirse desde el catálogo o la cola cuando no hay conexión. El mismo motor Web Audio decodifica el MP3 local y alimenta el AudioWorklet por bloques; se conservan pausa, volumen y avance. No hay peticiones REST durante una reproducción local. Si una transferencia de servidor falla y ya existe su copia, el controlador puede continuar desde la posición reproducida utilizando el archivo local.

Las canciones todavía no guardadas requieren conexión. Un búfer de streaming puede sonar hasta agotarse y no constituye una descarga completa. No se encolan solicitudes HTTP para ejecutarlas al reconectar. Al recuperar conexión, se actualiza el catálogo. `navigator.onLine` es una señal; una API caída se maneja con los errores existentes.

Las copias son de este navegador o aplicación instalada. Safari y una app añadida al Dock pueden utilizar almacenes separados: prepara las copias dentro de la app que utilizarás. El navegador puede borrar datos por falta de espacio o por una acción del usuario; no se promete conservación indefinida. Una actualización del service worker no elimina IndexedDB.

## Prueba local

Desde la raíz y con el entorno de Python activo:

```bash
python tools/build_catalog.py
```

Terminal S1:

```bash
python backend/server.py --port 5000 --server-id S1 --music .local_music/S1 --peer http://127.0.0.1:5001
```

Terminal S2:

```bash
python backend/server.py --port 5001 --server-id S2 --music .local_music/S2 --peer http://127.0.0.1:5000
```

Terminal frontend, desde la raíz:

```bash
cd frontend
npm ci
npm test
VITE_API_URLS="http://127.0.0.1:5000,http://127.0.0.1:5001" VITE_BASE_PATH="/SoundFlow/" npm run build
npm run preview:pwa
```

Abre `http://localhost:5173/SoundFlow/`. El puerto 5173 coincide con los orígenes CORS del backend local. Cierra antes cualquier `npm run dev` en ese puerto. Si guardaste otras URL, configura de nuevo los dos nodos locales desde la aplicación.

Para volver a desarrollo en el mismo origen, desregistra el worker desde las herramientas del navegador; de lo contrario puede seguir sirviendo la compilación anterior.

## Pruebas automatizadas

```bash
# Desde la raíz
python -m pytest -q
python tools/check_web_integration.py

# Desde frontend/
npm test
npx playwright install chromium
npm run test:pwa
```

La integración existente utiliza dos procesos Gunicorn y las canciones reales. Las pruebas PWA utilizan Chromium y una API local de prueba con PCM y un MP3 sintéticos para comprobar ámbito, manifiesto, iconos, recarga offline, biblioteca guardada, exclusión de API/audio, actualización con consentimiento, reproducción local sin HTTP, pausa/avance, límite de tres y rechazo de descargas incompletas. No usan cuentas ni modifican el despliegue público. La instalación desde el menú del navegador y la salida física de audio deben comprobarse manualmente.

## Evidencias y verificación pública

1. Abre la dirección HTTPS y espera el aviso de interfaz disponible sin conexión.
2. Comprueba en las herramientas del navegador el manifiesto y un registro con ámbito `/SoundFlow/`.
3. Reproduce desde S1 y S2; prueba avance, pausa y cola como en P06.
4. Instala y abre su icono. En Safari de Mac: Archivo → Añadir al Dock, si está disponible. En iPhone/iPad: Compartir → Añadir a pantalla de inicio.
5. Después de la primera visita conectada, desconecta la red y recarga: debe abrir la interfaz con aviso offline y biblioteca de referencia; las canciones no guardadas deben quedar deshabilitadas; las copias completas deben poder reproducirse.
6. Reconecta y comprueba que se actualiza la biblioteca y vuelve la reproducción.
7. Publica otra compilación: la versión anterior debe anunciar la actualización sin detener la música; al aceptar debe abrir la versión nueva.
8. Escucha cuatro canciones y espera que cada copia termine. Solo deben quedar tres. Prueba eliminar una y borrar todas.
9. Inspecciona Cache Storage: archivos de interfaz, sin rutas `/api/`, tickets ni audio PCM. En IndexedDB deben aparecer solo las copias MP3 completas y sus metadatos.

El AudioWorklet procesa sonido; el service worker administra solicitudes y archivos estáticos. Una PWA no garantiza reproducción en segundo plano indefinida: depende del navegador y del sistema operativo.

Referencias: [MDN: service workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers), [MDN: instalación](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable).
