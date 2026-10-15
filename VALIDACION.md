# Validación de la implementación P06

Fecha: 14 de octubre de 2026.
Base: commit `40ee67c52d116fe56807c06cf0b170d291796557` de la P04.

## Verificación ejecutada

18 pruebas automatizadas aprobadas en Linux, Python 3.12.14. Los servidores
se iniciaron realmente por HTTP en puertos dinámicos y HTTPS con certificado
firmado por una CA local. La salida del reproductor se probó con SDL dummy.

| Comprobación | Resultado |
|---|---|
| Tres nodos conectados en ciclo, catálogos diferentes | Unión correcta, sin ciclos de consulta |
| Misma canción con nombre distinto | Una entrada por hash de contenido |
| Canción solo en S2, cliente entra por S1 | Se asigna a S2 |
| Avance a 1.25 s | PCM igual al resultado de FFmpeg desde ese segundo |
| WAV, MP3, OGG y FLAC | Audio y búsqueda temporal comprobados |
| Doce sesiones simultáneamente reservadas | Sin antiguo máximo de ocho |
| CPU por encima del umbral configurado | Reserva rechazada temporalmente por recursos |
| Servidor poseedor en mantenimiento | Solicitud 202 en espera FIFO |
| Recuperación del servidor | Se asignan tickets en orden |
| Cancelación de ticket intermedio | Sale de la FIFO y se recalculan posiciones |
| Datos inválidos/canción inexistente/espera vencida | 400, 404 y estado de fallo 504 |
| Nodo previamente conocido inaccesible | Catálogo retenido y espera con vencimiento |
| Servidor de entrada caído y URL de respaldo | Cliente utiliza alternativa |
| Transporte interrumpido tras un bloque | Reanuda sin duplicar muestras PCM |
| HTTPS del servidor de audio y descubrimiento entre nodos | Verificación de certificado habilitada |
| Certificado no confiable | Requests rechaza la conexión |
| EOF temporal del archivo de búfer | Buffering y continuación; no fin prematuro |
| Pausa/reanudación en buffering y pista nueva | Estados correctos; stop antiguo no afecta nueva pista |
| Selección desde catálogo | Solicita audio sin exigir cola previa |
| Agregar varias pistas y vaciar cola | Panel visible/oculto; pista actual continúa |
| Avance desde interfaz y eventos tardíos | Nueva solicitud con start; datos antiguos descartados |
| Fin de cola | Consume siguientes una vez; no bucle automático |

También se revisaron la sintaxis de los archivos Python y de los cuatro scripts
Bash, y el comprobador de dependencias.

## Límites de esta verificación

Las acciones de la interfaz se probaron con dobles de widgets, no con una
ventana Tkinter renderizada. No fue posible validar gráficamente el diseño
ni escuchar audio en el entorno de ejecución. Se requiere probar la ventana,
la salida física de audio y los scripts de Windows en sus sistemas respectivos.
No se realizó una prueba nativa de macOS. No se desplegó ningún servicio.

## Prueba manual en tu Mac

1. Copia el paquete al repositorio conservando `.git/` y tu música. Activa el entorno.
2. Instala `requirements.txt` y ejecuta `python tools/check_environment.py`.
3. Ejecuta `python tools/prepare_demo.py`; arranca S1 y S2 como indica README.
4. Abre dos clientes y reproduce la exclusiva de S2 entrando por S1.
5. Confirma que el panel de cola empieza oculto; agrega varias pistas y verifica
   que aparece. Vacíala mientras escuchas: la actual debe continuar.
6. Arrastra la barra a 5 s y luego a 2 s. El tiempo mostrado debe empezar ahí.
7. Prueba pausa/continuar, volumen, siguiente y cambio rápido de canción.
8. Prueba también tus MP3 y observa el título/duración del catálogo.
9. Reinicia S2 con `--maintenance`, solicita su exclusiva y después vuelve a
   iniciarlo normalmente para demostrar espera y recuperación.
10. Genera los certificados y repite una reproducción con HTTPS y `--ca`.
11. Cierra clientes y servidores normalmente; comprueba que se limpia la caché.

Después de esta prueba podremos ajustar particularidades de tu instalación
antes de integrar `develop/p06` a `main`.
