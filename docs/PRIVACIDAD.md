# Política de privacidad

**Última actualización:** 26 de noviembre de 2026.
**Responsable del servicio:** Joel06777 (Fabián Joel Alarcón Macías).
**Contacto para privacidad:** `privacidad@tu-dominio.com`
⚠️ **Cambia esa dirección por tu correo real antes de publicar esta
política en la web.** Es un marcador de posición: el repositorio no
contiene ninguna dirección de contacto.

> Esta política describe lo que hace **este servicio de conversión**
> (el backend). La web que lo presenta corre en Vercel y solo reenvía el
> archivo al backend: no añade seguimiento propio. Si la web añade algún
> día analítica o cookies, habrá que actualizar esta política.

## En resumen

- Solo tratamos **el PDF que subes y el archivo que resulta de convertirlo**.
- **No pedimos cuenta, ni nombre, ni correo.** No hay registro de usuarios.
- El **PDF original se borra al terminar** cada conversión, siempre
  (también si da error o si cancelas).
- El **resultado se borra a los 60 minutos** como máximo.
- Los **logs no contienen el contenido de tus documentos**: ni texto, ni
  cifras, ni imágenes.
- **No vendemos ni compartimos tus documentos con nadie.** No se envía
  nada a servicios externos de conversión: el motor es propio y corre en
  nuestro servidor.
- **No hay seguimiento**: el backend no pone cookies de seguimiento ni
  usa analítica.

## Qué datos se tratan

| Dato | Para qué | Dónde vive |
|---|---|---|
| El PDF que subes | Convertirlo al formato que elegiste (Excel, Word o PowerPoint) | En el disco temporal del servidor, solo durante la conversión |
| El archivo convertido | Que puedas descargarlo | En el disco temporal del servidor, hasta 60 minutos |
| El nombre del archivo | Mostrarlo en el estado del trabajo y ponerle nombre a la descarga | En el estado del trabajo (`state.json`) y en los logs |
| Tu dirección IP | Limitar el uso a 60 conversiones por hora y por IP, para que nadie abuse del servicio gratuito | En Redis (contador con caducidad de 1 hora) o en memoria, si no hay Redis |
| Identificador del trabajo (`job_id`) | Saber qué trabajo es el tuyo al consultar el estado o descargar | En el estado del trabajo y en los logs |
| Errores de conversión | Decirte en español por qué falló (por ejemplo, «PDF protegido con contraseña») | En el estado del trabajo y en los logs |

**Lo que NO se recoge:** no hay cuentas, contraseñas, correos, nombres,
números de teléfono ni datos de pago. El servicio no sabe quién eres: solo
ve una IP y un archivo.

## Cómo se borran tus archivos (comportamiento real del código)

Esto no es una promesa genérica: es lo que hace el código
(`app/processing.py`, `app/jobs.py`, `app/worker.py`):

1. **El PDF original se borra al terminar la conversión.** El borrado está
   en un bloque `finally`: se ejecuta siempre, tanto si la conversión sale
   bien como si da error o si cancelas el trabajo. El original **no se
   conserva**.
2. **El resultado y todo el trabajo se borran a los 60 minutos.**
   Un limpiador automático revisa cada 5 minutos y borra los trabajos más
   viejos que `JOB_TTL_MINUTES` (60 minutos por defecto). Pasado ese
   tiempo, el enlace de descarga deja de funcionar y el trabajo ya no
   existe.
3. **Los enlaces de descarga caducan a los 15 minutos.** Están firmados con
   una clave secreta del servidor (HMAC) y llevan fecha de caducidad. Un
   enlace viejo no sirve para descargar nada.

Si cancelas un trabajo (`POST /api/v1/jobs/{id}/cancel`), el worker lo
detiene entre páginas y el original se borra igualmente.

## Los logs no contienen el contenido de tus documentos

Los logs del servidor (`app/jsonlog.py`) registran solo: identificador del
trabajo, formato de destino, estado, duración en segundos, número de
páginas y, si hay error, el **tipo** de error (por ejemplo,
`ValueError`). **Nunca** registran el texto, las cifras ni las imágenes
del PDF. El nombre del archivo sí queda en el log al crear el trabajo.

Las métricas públicas (`GET /metrics`) solo muestran contadores agregados
(trabajos por estado, duraciones, espacio en disco). No contienen datos de
ningún documento ni de ningún usuario.

## Con quién se comparte (con nadie)

- **No se vende nada a terceros.** Tus documentos no se venden, no se
  alquilan y no se comparten con anunciantes ni con otras empresas.
- **No se usa ningún servicio externo de conversión.** El PDF no sale del
  servidor hacia Google, Adobe ni ningún otro convertidor: se procesa con
  el motor propio (PyMuPDF, Tesseract/OCRmyPDF) instalado en el mismo
  servidor.
- **Tránsito por Vercel:** la web reenvía tu PDF desde tu navegador al
  backend pasando por una función serverless de Vercel
  (`web-example/api/convert.js`). Vercel solo lo transporta; no lo guarda
  como archivo ni lo convierte. El alojamiento del backend es Oracle Cloud
  (el servidor donde corre el servicio, en la región elegida al crear la
  cuenta).
- **HTTPS:** la conexión entre tu navegador y el servidor va cifrada
  (certificado gratuito de Let's Encrypt gestionado por Caddy).

## Cuánto tiempo se guardan los datos

| Dato | Tiempo máximo |
|---|---|
| PDF original | Hasta que termina la conversión (segundos o minutos) |
| Archivo convertido + estado del trabajo | 60 minutos |
| Contador de uso por IP | 1 hora |
| Logs del servidor | Viven en los logs de Docker del servidor, sin un plazo fijo configurado. No contienen contenido de documentos. Si necesitas que se borren antes, pide la eliminación (abajo) |

## Tus derechos y cómo pedir la eliminación

Como no hay cuentas, no hay un botón de «borrar mi cuenta». Pero puedes
pedir la eliminación de tus datos así:

1. **Espera 60 minutos**: tus archivos ya se habrán borrado solos. Es la
   vía más rápida y no necesita que hagas nada.
2. **Si necesitas que se borre antes**, escribe a
   `privacidad@tu-dominio.com` indicando el **identificador del trabajo**
   (`job_id`, el código que te dio la web al subir el PDF) y qué quieres
   que se borre. Borraremos el trabajo completo (original, resultado y
   estado) y te confirmaremos por correo.
3. Si crees que tus datos se han tratado mal, puedes reclamar ante la
   autoridad de protección de datos de tu país.

**Nota:** pasado el plazo de 60 minutos ya no queda nada que borrar: el
trabajo no existe ni en disco ni en los registros del servicio. Solo
quedarían las líneas de log (sin contenido del documento), que también
puedes pedir que se revisen.

## Cambios en esta política

Si cambia lo que hacemos con tus datos (por ejemplo, si se añade una
cuenta de usuario o analítica), se actualizará esta página y se indicará la
fecha del cambio arriba. La versión vigente es siempre la publicada en la
web.
