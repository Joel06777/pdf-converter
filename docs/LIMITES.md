# Límites conocidos (comunicar con honestidad)

Ningún motor propio iguala siempre a Adobe en todos los PDFs. Estos son los
casos que fallan o se degradan, y cómo los maneja la aplicación (avisar al
usuario en vez de entregar un resultado malo en silencio).

## Diseños complejos
- **Gráficos vectoriales dentro de tablas** (sparklines, gráficos de barras
  dibujados con vectores): se rasterizan como imagen en su posición. No quedan
  editables como datos.
- **Fuentes incrustadas raras o sin mapa de caracteres** (algunos PDF de
  imprenta antiguos): el texto puede salir con caracteres sustituidos. El
  informe `quality` muestra la cobertura < 100 % y qué quedó fuera.
- **Formularios XFA** (formularios dinámicos de Adobe): no se extraen los
  campos. La API devuelve error claro en español ("formulario dinámico (XFA)
  y no se puede convertir...") en vez de un archivo vacío.
- **Texto rotado 180° (boca abajo):** PowerPoint no admite rotación de 180° en
  cuadros de texto; se deja horizontal. El OCR propio endereza ±5° y OCRmyPDF
  corrige 90°/180°/270° solo en escaneos.
- **Texto vertical en Excel:** se conserva el texto y su posición, pero sin
  rotación de celda.

## OCR / escaneos
- **Escaneos borrosos, con sombras o manuscritos:** la precisión de cifras
  baja. Medido en escaneos limpios a 200 dpi: 100 % de cifras; en foto
  inclinada 3°: 100 % de cifras pero 85,5 % de texto. En escaneos malos la
  cifra puede caer por debajo del 97 %: por eso existe `ocr_warning` y el
  resaltado amarillo de celdas dudosas en Excel.
- **Sellos y marcas de agua de color sobre el texto:** la binarización los
  atenúa, pero un sello oscuro sobre una cifra puede hacer que se pierda.
- **Escritura manuscrita:** no soportada (Tesseract está entrenado para texto
  impreso).
- **Idiomas:** OCR en español + inglés (`spa+eng`). Otros idiomas necesitan
  instalar su paquete `tesseract-ocr-<idioma>` y cambiar `OCR_LANG`.

## Tablas
- **Tablas sin líneas ni alineación clara** (columnas que se tocan): la
  cuadrícula visual puede fusionar columnas. La cobertura numérica lo delata
  (una cifra que se pega a otra deja de ser número).
- **Fórmulas de totales:** solo se escriben cuando la suma coincide con lo
  impreso. Si el PDF tiene un total que no es suma de la columna (p. ej.
  saldo arrastrado), la cifra se deja como valor, sin fórmula.
- **Varias tablas en una página:** se reconstruye una sola cuadrícula por
  página; dos tablas separadas verticalmente quedan en la misma hoja, una
  debajo de otra (correcto), pero sin separación explícita de "tabla 1 / 2".

## API y operación
- **Límite:** 50 MB y 200 páginas por archivo; 60 conversiones/hora por IP
  por defecto; resultados borrados a los 60 minutos.
- **PDF con contraseña:** error claro, no se intenta adivinarla.
- **Archivos de más de 200 páginas:** se rechazan antes de convertir.
- **Prueba de carga de 200 usuarios concurrentes:** el script está en
  `scripts/loadtest/` pero **no se ejecutó a esa escala en este entorno**
  (ver `scripts/loadtest/README.md`).
