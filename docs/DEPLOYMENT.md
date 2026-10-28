# Despliegue de SoundFlow: Render y GitHub Pages

P07 amplía el frontend de P06 con una PWA. Conserva los servicios existentes:

| Componente | Dirección |
|---|---|
| Aplicación | https://sangrador21.github.io/SoundFlow/ |
| S1 | https://soundflow-s1.onrender.com |
| S2 | https://soundflow-s2.onrender.com |

## Desarrollo e integración

Trabaja en `feature/pwa-p07`, creada desde `main`. Aplica los cambios y verifica la compilación según [PWA.md](PWA.md). Después de revisar `git status`:

```bash
git add -A
git commit -m "Adapta SoundFlow a PWA instalable con service worker"
git push -u origin feature/pwa-p07
```

**Checks** incluye las pruebas existentes y la verificación PWA en Chromium. El push de la rama de trabajo no publica automáticamente en Pages. Abre un PR hacia `main` y revisa sus resultados.

Después de verificar la versión puedes integrar el PR o hacer el merge local:

```bash
git switch main
git pull --ff-only origin main
git merge --no-ff feature/pwa-p07 -m "Integra SoundFlow P07 como aplicacion PWA"
git push origin main
```

No hagas ambos tipos de merge. Si integraste el PR en GitHub, solo actualiza tu `main` local con `git pull --ff-only origin main`.

## GitHub Pages

- Settings → Pages → Source debe seguir siendo **GitHub Actions**.
- El entorno `github-pages` debe permitir `main`.
- Conserva la variable de repositorio `SOUNDFLOW_API_URLS`:

  ```text
  https://soundflow-s1.onrender.com,https://soundflow-s2.onrender.com
  ```

- `pages.yml` publica al subir cambios a `main`; también admite ejecución manual, sujeta a las reglas del entorno.
- La base se obtiene del repositorio: `/SoundFlow/`. La compilación genera el manifiesto, `sw.js`, iconos, fuentes y AudioWorklet para esa ruta.
- No subas `frontend/dist/`: lo genera Actions.

Una versión PWA anterior abierta ofrece **Actualizar ahora** al detectar el nuevo worker. P06 no tenía worker; recibirá la PWA al recargar después del despliegue.

## Render

No se necesitan nuevos servicios ni cambios de contratos. `render.yaml` conserva Docker, `main` y `/api/health`.

| Variable | S1 | S2 |
|---|---|---|
| `SOUNDFLOW_NODE_ID` | `S1` | `S2` |
| `SOUNDFLOW_PEERS` | `https://soundflow-s2.onrender.com` | `https://soundflow-s1.onrender.com` |
| `SOUNDFLOW_CORS_ORIGINS` | `https://sangrador21.github.io` | `https://sangrador21.github.io` |
| `SOUNDFLOW_WAIT_TIMEOUT` | `120` | `120` |
| `SOUNDFLOW_PEER_TIMEOUT` | `2` | `2` |
| `SOUNDFLOW_CLUSTER_TOKEN` | Token privado compartido | El mismo token |

El token permanece en Render. No se copia al frontend, al manifiesto ni a variables `VITE_*`. El origen CORS no incluye `/SoundFlow/`. Las URL públicas usan HTTPS; Render termina TLS en su proxy. No se desactiva la validación de certificados.

Las imágenes preparan cada biblioteca desde los originales de `music/` y los manifiestos de `deploy/catalogs/`. No se versionan las copias de `.local_music/`. Gunicorn mantiene un único worker con varios hilos porque las sesiones y FIFO están en memoria.

Si Render reconstruye los servicios tras el merge, espera a que estén desplegados antes de probar. Un reinicio pierde las sesiones de ese nodo y puede requerir una nueva asignación.

## Cierre

Verifica instalación, reproducción y desconexión según [PWA.md](PWA.md). Solo después de validarlo en público puedes crear una etiqueta de P07:

```bash
git tag -a p07-final -m "Practica 07: SoundFlow PWA desplegada y validada"
git push origin p07-final
```

Conserva las etiquetas de P06 como referencia de la práctica anterior.
