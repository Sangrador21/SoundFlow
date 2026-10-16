# Despliegue de SoundFlow: Render y GitHub Pages

Esta guía utiliza el repositorio `Sangrador21/SoundFlow`, dos servicios de Render y una página de GitHub Pages. Los nombres públicos definitivos de Render se obtienen del panel después de crear los servicios; no deben sustituirse por URL inventadas.

## 1. Comprobar y publicar la rama

Trabaja en `feature/web-p06`, creada desde la versión estable. Antes de subir:

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/build_catalog.py
python -m pytest -q
cd frontend
npm ci
npm test
npm run build
cd ..
```

Prueba también los dos servidores locales y el navegador como indica el README.

Después de revisar `git status`:

```bash
git add -A
git commit -m "Adapta SoundFlow a cliente web y prepara despliegue"
git push -u origin feature/web-p06
```

El workflow de Pages se omite mientras la variable `SOUNDFLOW_API_URLS` esté vacía. Es normal en este primer push. El workflow Checks sí se ejecuta; revisa sus resultados antes de continuar.

## 2. Crear los dos servicios en Render

1. En Render, entra en **New → Blueprint**.
2. Conecta tu repositorio de GitHub y selecciona la rama **feature/web-p06**.
3. Render detectará el archivo `render.yaml`, que declara los servicios **soundflow-s1** y **soundflow-s2**, ambos con Docker y plan Free.
4. Cuando solicite `SOUNDFLOW_CLUSTER_TOKEN` para cada servicio, introduce **el mismo valor** en ambos. Puedes generarlo en tu propia terminal:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Mantén ese valor en Render; no lo agregues al repositorio ni al frontend.

5. Revisa los recursos y confirma la creación desde tu cuenta.
6. Espera a que ambos servicios estén desplegados. Anota sus dos URL HTTPS reales.
7. Abre cada URL seguida de `/api/health`. Una debe responder con `server_id: S1` y la otra con `server_id: S2`.

Los nombres pueden incluir un sufijo asignado por Render. Usa las URL exactas del panel.

### Cómo se separan las canciones

Render pasa `SOUNDFLOW_NODE_ID` al proceso de construcción de Docker como argumento de build. La primera etapa de la imagen selecciona únicamente los archivos de `deploy/catalogs/S1.json` o `S2.json`. La imagen final recibe solo esa biblioteca.

Las canciones originales deben seguir versionadas en `music/`, como ya están en el repositorio. No necesitas subir `.local_music/`, `music/S1/` ni `music/S2/`. Para añadir otra canción al despliegue, incorpora su archivo a `music/`, actualiza el manifiesto del nodo y vuelve a desplegar. La distribución incluida asigna 12 canciones a cada nodo, con 6 compartidas: el catálogo agregado contiene las 18 canciones MP3 originales. El tono de prueba queda fuera. No subas copias de las carpetas generadas.

Las pruebas calculan los conteos y la ubicación esperados desde los manifiestos y el SHA-256 de los audios; no esperan una cantidad fija. Agregar una canción requiere únicamente incorporar el archivo y asignarlo a uno o ambos manifiestos. Conserva canciones compartidas y exclusivas por nodo para las demostraciones de distribución.

### Alternativa: crear servicios manualmente

Si no usas Blueprint, crea dos **Web Services** con estos campos:

| Campo | Valor |
|---|---|
| Repositorio | `Sangrador21/SoundFlow` |
| Rama | `feature/web-p06` |
| Runtime | Docker |
| Root Directory | Vacío; utilizar la raíz del repositorio |
| Dockerfile Path | `./Dockerfile` |
| Docker Build Context | `.` |
| Docker Command | Vacío; utilizar el CMD de la imagen |
| Health Check Path | `/api/health` |
| Plan | Free, para la demostración |

Configura las variables de la siguiente sección antes del build; `SOUNDFLOW_NODE_ID` determina qué archivos recibe la imagen. No utilices como Start Command `python server.py` ni `gunicorn app:app`: la imagen ya tiene la entrada adecuada.

## 3. Conectar los pares y configurar CORS

En **Environment** de cada servicio, verifica estos valores:

| Variable | S1 | S2 |
|---|---|---|
| `SOUNDFLOW_NODE_ID` | `S1` | `S2` |
| `SOUNDFLOW_PEERS` | URL HTTPS real de S2 | URL HTTPS real de S1 |
| `SOUNDFLOW_CORS_ORIGINS` | `https://sangrador21.github.io` | `https://sangrador21.github.io` |
| `SOUNDFLOW_WAIT_TIMEOUT` | `120` | `120` |
| `SOUNDFLOW_PEER_TIMEOUT` | `2` | `2` |
| `SOUNDFLOW_CLUSTER_TOKEN` | Tu token compartido | Exactamente el mismo token |

Guarda y despliega de nuevo para aplicar la configuración. No incluyas `/api` ni otra ruta en los valores de `SOUNDFLOW_PEERS`.

No configures `SOUNDFLOW_BASE_URL` como localhost: Render proporciona automáticamente `RENDER_EXTERNAL_URL`, que la aplicación utiliza para anunciar su dirección pública.

Render termina HTTPS en su proxy y envía HTTP al proceso interno. El cliente y los pares utilizan las URL públicas HTTPS, con verificación normal de certificados. No copies `certs/` al servicio ni desactives la validación TLS.

Abre la URL de S1 seguida de `/api/catalog`. Debe mostrar **dos nodos y el catálogo completo definido en los manifiestos** (18 canciones únicas con la distribución incluida). Si solo aparece un nodo, verifica las URL de los pares y vuelve a actualizar cuando ambos estén activos.

Si utilizas Blueprint y posteriormente sincronizas de nuevo su configuración, conserva también las URL reales de `SOUNDFLOW_PEERS` en el `render.yaml` de tu rama; son direcciones públicas y pueden versionarse. El token continúa solo en el panel.

## 4. Preparar GitHub Pages

En el repositorio de GitHub:

1. Entra en **Settings → Pages**.
2. En **Build and deployment → Source**, selecciona **GitHub Actions**.
3. Si existe una protección en **Settings → Environments → github-pages**, permite desplegar desde `feature/web-p06` y `main` en **Deployment branches and tags**.
4. Entra en **Settings → Secrets and variables → Actions → Variables**.
5. Crea una **Repository variable** llamada `SOUNDFLOW_API_URLS`.
6. Como valor, escribe las dos URL HTTPS reales de Render separadas por una coma, sin `/api`. Es configuración pública del frontend; no es el token del clúster.

El workflow utiliza `VITE_BASE_PATH=/SoundFlow/` a partir del nombre del repositorio. Así funcionan los recursos, las fuentes y el AudioWorklet desde una página de proyecto de GitHub Pages.

## 5. Activar la publicación web

Una vez configuradas las URL y Pages, dispara otro push desde tu rama:

```bash
git commit --allow-empty -m "Activa publicacion web con las API de Render"
git push
```

Esto inicia **Publish web to GitHub Pages**. Revisa su ejecución en **Actions**. Instala las dependencias bloqueadas por `package-lock.json`, ejecuta las pruebas y construye y publica el frontend.

La URL esperada para este repositorio es:

**https://sangrador21.github.io/SoundFlow/**

La publicación está confirmada cuando el job de Pages termina correctamente y proporciona su URL. Si el workflow está omitido, revisa que la variable se llame exactamente `SOUNDFLOW_API_URLS` y contenga un valor.

## 6. Verificación pública

Con ambos servicios activos:

1. Abre la página desde una computadora o teléfono sin ejecutar servidores locales.
2. Comprueba que la biblioteca coincide con los manifiestos y muestra los nodos S1 y S2 (18 canciones únicas inicialmente).
3. Reproduce una exclusiva de cada nodo y revisa **Servidores**. La tarjeta de reproducción indica el nodo que entrega el audio.
4. Prueba pausa, continuación, volumen y avance hacia adelante y atrás.
5. Agrega varias canciones, comprueba el avance automático y vacía la cola durante la reproducción.
6. Abre otra pestaña o dispositivo para representar otro cliente.
7. Verifica que los documentos, fuentes, JavaScript, peticiones y AudioWorklet se carguen sin errores en las herramientas de desarrollo del navegador.

Para probar FIFO, configura temporalmente `SOUNDFLOW_MAINTENANCE=true` en S2 y vuelve a desplegar. Solicita desde S1 una canción exclusiva de S2. Cambia después la variable a `false` y despliega de nuevo antes de que venza el ticket; para esta demostración puedes aumentar `SOUNDFLOW_WAIT_TIMEOUT`, porque un despliegue puede tardar más de dos minutos. El reinicio de S1 perdería sus tickets, por lo que modifica solo S2.

Para una prueba de espera más rápida, utiliza los servidores locales y `--maintenance`, sin esperar una reconstrucción de imagen.

## 7. Integrar la versión web estable

Después de verificar el despliegue y con el árbol de trabajo limpio:

```bash
git switch main
git pull --ff-only origin main
git merge --no-ff feature/web-p06 -m "Integra cliente web y despliegue de SoundFlow"
git push origin main
git tag -a p06-web-final -m "Practica 06 web desplegada y validada"
git push origin p06-web-final
```

La etiqueta `p06-final` continúa apuntando a la versión de escritorio anterior. No la muevas ni la borres.

Para mantener los despliegues futuros desde `main`, cambia en Render la rama de los servicios y, si utilizas Blueprint, su rama de origen y las entradas `branch` de `render.yaml` a `main`. Versiona ese ajuste. GitHub Pages ya contempla los pushes de `main`.

## Consideraciones del alojamiento

- Los servicios gratuitos pueden entrar en reposo después de 15 minutos sin tráfico. La primera consulta puede tardar aproximadamente un minuto. Para presentar la práctica, abre previamente `/api/health` de los dos nodos y después actualiza la biblioteca.
- Los servicios gratuitos comparten los límites de horas y transferencia del workspace. Son adecuados para la demostración, pero no implican ejecución ilimitada.
- El disco de ejecución es efímero; la música incluida en la imagen se recupera al reconstruir o reiniciar. Las sesiones y los tickets en memoria no se conservan tras reinicios.
- Mantén un único worker WSGI por nodo y no utilices `--preload`. Aumentar procesos sin compartir el estado rompería la afinidad entre tickets y sesiones.
- CORS limita qué páginas pueden leer las respuestas en un navegador; no sustituye autenticación de usuarios. Esta práctica no implementa cuentas de oyentes.

Referencias de las plataformas:

- [Docker en Render y argumentos de construcción](https://render.com/docs/docker)
- [Servicios web y HTTPS en Render](https://render.com/docs/web-services)
- [Límites de los servicios gratuitos](https://render.com/docs/free)
- [Despliegue de Vite en GitHub Pages](https://vite.dev/guide/static-deploy.html)
