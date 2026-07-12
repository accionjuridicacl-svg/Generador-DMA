# Servicio web - Generador DMA

Este es el "cerebro" que Make va a llamar por HTTP. No necesitas tocar código,
solo desplegarlo una vez.

## Desplegar en Render.com (gratis, sin terminal)

1. Crea una cuenta en https://render.com (puedes entrar con tu cuenta de Google).
2. Crea un repositorio en GitHub (github.com -> "New repository") y sube estos
   5 archivos arrastrándolos a la página del repo (botón "Add file" > "Upload files").
   No necesitas saber Git, la web de GitHub permite subir archivos directo.
3. En Render: "New +" -> "Web Service" -> conecta tu cuenta de GitHub -> elige
   el repositorio que acabas de crear.
4. Render detecta el Dockerfile automáticamente. Déjalo con la configuración
   por defecto (plan "Free") y click "Create Web Service".
5. Espera 2-3 minutos a que compile. Cuando diga "Live", copia la URL that te
   da arriba (algo como https://generador-dma-xxxx.onrender.com).
6. Esa URL es la que usas en Make.com:
   - POST  {url}/extraer   (adjuntas el PDF del certificado)
   - POST  {url}/generar   (mandas el JSON del caso, te devuelve el .docx)

Nota: el plan gratis de Render "duerme" el servicio si no se usa por 15 min,
y tarda ~30 segundos en despertar en la primera llamada del día. Para un
estudio con pocos casos diarios esto no debería ser un problema; si más
adelante molesta, se puede subir al plan pagado (US$7/mes) para que esté
siempre despierto.

## Endpoints

### GET /
Healthcheck. Devuelve `{"status": "ok"}` si el servicio está corriendo.

### POST /extraer
Body: form-data con campo `file` = el PDF del certificado.
Devuelve JSON con los datos extraídos (nombre, RUT, fechas, etc.)

### POST /generar
Body: JSON `{"context": {...}}` con el caso completo (mismo formato que
usa docxtpl / la plantilla).
Devuelve el archivo .docx generado, listo para descargar.
