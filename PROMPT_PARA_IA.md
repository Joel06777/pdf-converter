# PROMPT PARA LA IA (copia desde aquí hasta el final)

Eres un ingeniero de software senior. Vas a continuar y mejorar un proyecto que ya existe en este repositorio: un **convertidor de PDF a Word (.docx), Excel (.xlsx) y PowerPoint (.pptx)** que funciona de forma **100% independiente**, sin APIs ni servicios de terceros (nada de Adobe, ConvertAPI, CloudConvert, Google, etc.). Solo librerías de código abierto que corren dentro de nuestros propios servidores.

Lee primero `README.md` y todo el código de `app/`. Ya hay una primera versión funcional con pruebas que pasan. Tu trabajo es **mantenerla funcionando, ampliarla y llevar la fidelidad lo más cerca posible del 100%**, sin romper las pruebas existentes.

## 1. Contexto del negocio

- El dueño tiene una página web en **GitHub + Vercel** que ofrece herramientas PDF. Esta aplicación es el **servicio de conversión** al que esa página se conecta por HTTP.
- Debe atender hasta **10.000 usuarios** (no simultáneos todos a la vez: planifica para ~200 conversiones concurrentes en hora pico y colas para el resto).
- Idioma de los usuarios: **español** (documentos contables, formularios, reportes, contratos). Incluye acentos, ñ, símbolos de moneda ($) y números con formato contable.
- Vercel NO puede ejecutar la conversión (límites de tamaño y tiempo). Por eso la conversión corre en un backend propio (Docker) y la web solo sube el PDF, consulta el estado y descarga el resultado.

## 2. Requisitos obligatorios

1. **Independencia total**: prohibido llamar a servicios externos de conversión. Se permiten: PyMuPDF, pdf2docx, python-docx, python-pptx, openpyxl, Tesseract/OCRmyPDF, LibreOffice (solo como herramienta local opcional de verificación), Pillow, NumPy.
2. **Tres conversiones**: PDF→Excel, PDF→Word, PDF→PowerPoint, más una pantalla de ejemplo para la web.
3. **PDF con texto y PDF escaneado**: los escaneados pasan por OCR propio (español + inglés). Antes del OCR se deben limpiar las líneas de tabla y binarizar la imagen (ya implementado en `app/converters/extract.py`; mejóralo con enderezado de páginas inclinadas y manejo de fotos tomadas con celular).
4. **Fidelidad visual y de datos** (ver sección 3).
5. **Seguridad y privacidad**: el PDF original se borra al terminar; los resultados se borran a los 60 minutos; límite de tamaño (50 MB) y de páginas (200); validación de que el archivo sea un PDF real; manejo claro de PDFs con contraseña; límite de conversiones por IP/hora; CORS restringido al dominio de la web; clave de API opcional. No registrar el contenido de los documentos en los logs.
6. **Escalabilidad**: API (FastAPI) + cola (Celery + Redis) + workers escalables (`docker compose up --scale worker=N`). Ningún estado en memoria de la API que impida tener varias réplicas.
7. **Errores claros en español** para el usuario final (archivo dañado, protegido, demasiado grande, sin texto reconocible, etc.). Nunca un error genérico ni una conversión "silenciosamente mala".

## 3. Qué significa "calidad 100%" (criterios medibles)

No se puede prometer 100% en cualquier PDF imaginable, así que se define así y se **mide con pruebas automáticas**:

**Para PDFs con texto nativo**
- Cobertura de texto = 100 %: todas las palabras del PDF aparecen en el archivo convertido.
- Cobertura numérica = 100 %: todas las cifras aparecen como **valores numéricos reales** en Excel (no como texto), con el formato original (`#,##0.00`, `"$"#,##0.00`, negativos entre paréntesis, porcentajes). Códigos como RUC, cédulas, teléfonos y fechas con guiones permanecen como texto (no convertirlos a número).
- Excel: se conservan colores de relleno, negritas, fuentes, bordes, celdas combinadas, anchos de columna, alturas de fila, imágenes (logos, QR, firmas) y orientación/tamaño de impresión. La hoja renderizada (LibreOffice → PDF → imagen) debe verse prácticamente igual al original.
- Word: documentos tipo tabla/reporte salen como tabla de ancho fijo fiel al original; documentos de texto corrido conservan párrafos, columnas, tablas, imágenes y estilos.
- PowerPoint: una diapositiva por página, con el mismo tamaño, todo editable (cuadros de texto, formas, imágenes).

**Para PDFs escaneados**
- Precisión de cifras del OCR ≥ 97 % en escaneos limpios a 200 dpi o más (hoy la prueba del repositorio alcanza 100 % sobre el documento de referencia). Mide también precisión de texto (distancia de edición). Cuando la confianza del OCR sea baja, la respuesta debe incluir una advertencia en español para que el usuario revise esas celdas, y se deben resaltar visualmente las celdas dudosas en el Excel.

**Regla de oro**: cada conversión devuelve un objeto `quality` (ya existe en `app/converters/verify.py`) y la web debe mostrarlo al usuario. Si la cobertura es < 100 %, se muestra qué quedó fuera.

## 4. Documento de referencia (obligatorio)

El archivo `tests/fixtures/estado_ingresos_octubre_2026.pdf` es un flujo de caja real (Asociación de Propietarios de la Urbanización Punta Esmeralda). Tiene: logo, bloques con relleno verde, cifras contables con símbolo `$` separado, títulos que ocupan dos líneas, firmas con código QR y sello de tiempo. **Ningún cambio puede hacer que sus pruebas fallen.** Úsalo como patrón para crear más casos de prueba.

Crea además una carpeta `tests/fixtures/` con otros PDFs de prueba (puedes generarlos con código): facturas, estados de cuenta con varias páginas, tablas sin líneas, tablas con celdas combinadas, documentos a dos columnas, texto con acentos, PDF escaneado y foto de documento ligeramente inclinada. Para cada uno, escribe un test con criterios de la sección 3.

## 5. Tareas a realizar, en este orden

1. Instala dependencias, ejecuta `pytest` y confirma que todo pasa. Si no, corrige antes de avanzar.
2. **Ampliar la batería de pruebas** (sección 4) y registrar métricas de fidelidad por tipo de documento en `docs/METRICAS.md`.
3. **Mejorar Excel**: detección de tablas sin líneas, varias tablas en una página, celdas combinadas verticales, fórmulas de totales opcionales (solo si el PDF indica claramente un total; nunca inventar datos), una hoja por página o una sola hoja continua (parámetro `layout=pages|continuous`).
4. **Mejorar Word**: tablas con celdas combinadas verticales, encabezados/pies de página, saltos de página, listas, columnas; evitar que textos se solapen con imágenes.
5. **Mejorar PowerPoint**: texto en varias líneas dentro de un mismo cuadro, rotaciones, tablas como tablas nativas de PowerPoint cuando sea posible.
6. **OCR**: enderezado automático, detección de rotación de página, mapa de confianza por palabra, soporte para escaneos en color con sellos y marcas de agua.
7. **API**: endpoint de progreso por página, cancelación de trabajos, subida de varios archivos, y firma temporal en la URL de descarga.
8. **Frontend de ejemplo** en `web-example/` (HTML + JavaScript puro, sin frameworks): arrastrar y soltar, elegir destino, barra de progreso consultando `/api/v1/jobs/{id}`, mostrar el informe de calidad y descargar. Debe poder copiarse al proyecto de Vercel existente. La clave de API NUNCA va en el navegador: crea una función serverless en Vercel (`/api/convert.js`) que reenvía la petición al backend con la clave guardada en una variable de entorno.
9. **Despliegue**: guía paso a paso en `docs/DESPLIEGUE.md` para un VPS (Docker Compose + Caddy o Nginx con HTTPS) y alternativa en Google Cloud Run/Fly.io; configuración de GitHub Actions (`.github/workflows/ci.yml`) que ejecute las pruebas en cada push.
10. **Prueba de carga** con `locust` o `k6` en `scripts/loadtest/`: simula 200 usuarios concurrentes con PDFs de 1, 10 y 50 páginas; reporta tiempos p50/p95 y cuántos workers hacen falta. Documenta los resultados reales; no inventes cifras.
11. **Observabilidad**: logs en JSON sin datos del documento, métricas Prometheus (`/metrics`: trabajos por estado, duración, fallos), y endpoint `/health` que verifique Redis y espacio en disco.

## 6. Reglas de trabajo

- Código en Python 3.12, con tipos y funciones pequeñas; comentarios y mensajes al usuario en **español**.
- Cada cambio nuevo lleva su prueba. No elimines pruebas para que "pasen".
- No agregues dependencias que llamen a servicios externos ni que requieran licencias de pago. Antes de agregar una dependencia, verifica su licencia (se aceptan MIT, BSD, Apache-2.0, MPL; **PyMuPDF es AGPL/comercial**: avisa al dueño en `docs/LICENCIAS.md` y propone la alternativa o el cumplimiento de la licencia).
- No inventes resultados: si no puedes ejecutar algo (por ejemplo, una prueba de carga real), dilo y deja el script listo.
- Entrega al final un resumen con: qué se hizo, métricas medidas, límites conocidos y qué falta.

## 7. Límites que debes comunicar honestamente

- Ningún motor propio iguala siempre a Adobe en diseños extremadamente complejos (gráficos vectoriales dentro de tablas, fuentes incrustadas raras, formularios XFA). Documenta en `docs/LIMITES.md` los casos conocidos que fallan y cómo los maneja la aplicación (avisar al usuario en vez de entregar un resultado malo).
- Los escaneos de mala calidad (borrosos, con sombras, manuscritos) pueden contener errores de OCR; por eso existe el informe de calidad y el resaltado de celdas dudosas.

# FIN DEL PROMPT
