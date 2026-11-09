# Publicación P08 en Render y GitHub Pages

Primero aplica y prueba la rama `feature/microservices-p08` localmente. La entrega no cambia cuentas, configura servicios ni publica automáticamente.

## Preparar los cinco servicios

La configuración P08 está en **`deploy/render.p08.yaml`**. Crea un Blueprint nuevo seleccionando esa ruta y la rama de trabajo; el `render.yaml` de raíz mantiene la P07. Las imágenes no importan el servidor monolítico anterior.

| Servicio propuesto | Dockerfile | Variables específicas |
|---|---|---|
| soundflow-p08-media-s1 | deploy/docker/Dockerfile.media | SOUNDFLOW_NODE_ID=S1 |
| soundflow-p08-media-s2 | deploy/docker/Dockerfile.media | SOUNDFLOW_NODE_ID=S2 |
| soundflow-p08-catalog | deploy/docker/Dockerfile.catalog | SOUNDFLOW_MEDIA_NODES |
| soundflow-p08-playback | deploy/docker/Dockerfile.playback | SOUNDFLOW_MEDIA_NODES y SOUNDFLOW_CATALOG_URL |
| soundflow-p08-gateway | deploy/docker/Dockerfile.gateway | SOUNDFLOW_CATALOG_URL y SOUNDFLOW_PLAYBACK_URL |

Todos usan la raíz como Docker context, `/api/health`, un worker Gunicorn e identifican su rol mediante `SOUNDFLOW_SERVICE`. Render convierte SOUNDFLOW_NODE_ID en argumento de construcción para preparar el manifiesto correcto de medios; S2 debe construirse con S2. El Blueprint comparte un secreto generado mediante el grupo `soundflow-p08-internal`.

El archivo propone URL a partir de los nombres anteriores. **Comprueba las URL realmente asignadas por Render**, que pueden tener sufijo si el nombre no está disponible. Corrige el JSON SOUNDFLOW_MEDIA_NODES en catálogo y reproducción y las URL de sus dependencias en gateway/reproducción. Usa las bases HTTPS, sin `/api`.

Ejemplo de registro de medios:

```json
{"S1":"https://soundflow-p08-media-s1.onrender.com","S2":"https://soundflow-p08-media-s2.onrender.com"}
```

Los medios y el gateway deben permitir el origen `https://sangrador21.github.io` en SOUNDFLOW_CORS_ORIGINS, sin `/SoundFlow/`. Las URL de medios que recibe el navegador se obtienen de RENDER_EXTERNAL_URL. Solo sobrescribe SOUNDFLOW_BASE_URL si tienes una base pública distinta.

Las instancias Free no reciben tráfico privado, por lo que el Blueprint utiliza HTTPS público para las llamadas internas, protegidas por el token. Con instancias pagadas/red privada se pueden cambiar las URL de transporte sin cambiar las URL públicas anunciadas por medios.

## Comprobar antes de conectar la PWA

1. Espera a que los cinco servicios terminen su despliegue.
2. Abre `/api/health` de cada uno. Deben informar versión **0.8.0**, roles gateway/catalog/playback/media y S1/S2 correctos. Los medios anuncian `offline-download`.
3. Abre `/api/services` en el gateway: catálogo y reproducción deben estar `ok`.
4. Abre `/api/catalog` en el gateway: debe mostrar los dos medios y el catálogo de los manifiestos. `entrypoints` debe contener el gateway.
5. En un servicio dormido Free, la primera petición puede tardar en despertarlo. Abre su health, espera y vuelve a consultar; un 503 de una dependencia no indica que ya esté preparada.

Solo health es liveness; `/api/services` comprueba las dependencias de control y `/api/catalog` comprueba los medios. Repetir un despliegue del frontend no actualiza los servicios de backend.

## Cambiar el frontend

En GitHub Settings → Secrets and variables → Actions → Variables, cambia **SOUNDFLOW_API_URLS** por la URL del gateway P08, por ejemplo:

```text
https://soundflow-p08-gateway.onrender.com
```

No coloques aquí catálogo, reproducción, S1, S2 ni el token. Se admite más de un gateway configurado, pero esta entrega despliega uno y no ofrece alta disponibilidad del plano de control.

Después de que Checks pase y la revisión local sea correcta, integra la rama a main. Pages sigue publicando desde main. En el Blueprint P08 cambia también la rama de los cinco servicios a main (actualiza `deploy/render.p08.yaml`) para que futuras versiones usen esa rama. No elimines la rama de trabajo antes de cambiar la configuración de Render.

Espera la publicación y acepta **Actualizar ahora** en una PWA abierta. La configuración P08 de direcciones usa otra clave de localStorage para no reutilizar S1/S2 de P07 como coordinadores. La caché estática se versiona; las copias completas existentes en IndexedDB no se borran.

## Recursos y persistencia

Cinco servicios Free comparten la cuota de horas del workspace; no son 750 horas para cada uno. Se despiertan bajo demanda y la cadena de arranque puede necesitar varias consultas iniciales. Comprueba el plan y las cuotas disponibles en tu cuenta antes de crear servicios adicionales. No se añaden Redis, Kafka, Kubernetes ni bases externas a esta práctica.

SQLite se almacena en `/app/state/playback.sqlite3`. En Compose su volumen conserva los tickets. En Render Free no hay disco persistente y los redeploys pueden perderlos. No se usa esta SQLite como base compartida ni se afirma alta disponibilidad. Los MP3 de medios forman parte de cada imagen; las copias offline viven en el dispositivo del oyente.

Mantén la P07 accesible hasta comprobar la P08 publicada. Conserva `p06-final` y `p07-final`. Crea `p08-final` únicamente después de validar instalación, catálogo, reproducción, avance, FIFO/cancelación, desconexión y reconexión en la nueva publicación.

Referencias: [Render Blueprints](https://render.com/docs/blueprint-spec), [Docker en Render](https://render.com/docs/docker), [Render Free](https://render.com/docs/free).
