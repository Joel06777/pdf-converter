# Casos hostiles y defectuosos (web/tests/)

Generados con `node web/tests/generate-hostile-pdfs.mjs` (sin
dependencias: construye los bytes del PDF a mano). Sirven para
comprobar que el motor del navegador **nunca se cuelga, nunca se cae
la página y siempre responde en español** ante un PDF malo.

La columna «Resultado» está en **sin medir**: se rellena corriendo
`web/tests/index.html` cuando el motor exista. Hoy el motor no
existe (`web/engine/` vacío), así que ningún caso está medido.

| Caso | Qué es | Lo que debe pasar (esperado) | Resultado |
|---|---|---|---|
| `01-valido.pdf` | PDF mínimo válido, 1 página con «Hola» | Se abre y se convierte bien (control) | sin medir |
| `02-truncado.pdf` | Faltan xref, trailer y `%%EOF` | Error claro: «parece estar dañado o incompleto» | sin medir |
| `03-cifrado.pdf` | Cifrado real AES-256 (PyMuPDF), contraseña de usuario «secreta» | Error claro: «tiene contraseña» (no se intenta adivinarla) | sin medir |
| `04-xref-roto.pdf` | Offsets del xref apuntando a cualquier parte | Se abre (el lector reconstruye el xref) o error claro; nunca se cuelga | sin medir |
| `05-paginas-mentirosas.pdf` | Declara 10.000 páginas, tiene 1 | Se convierte solo la página real; el conteo falso no reserva memoria para 10.000 | sin medir |
| `06-xfa.pdf` | Formulario dinámico XFA de Adobe | Error claro: «formulario dinámico (XFA), no se puede convertir» | sin medir |
| `07-length-mentiroso.pdf` | Un flujo que declara 999.999.999 bytes | No reserva esa memoria; error claro o conversión de lo que hay | sin medir |
| `08-bucle.pdf` | El catálogo se referencia a sí mismo | No entra en bucle infinito; error claro o apertura | sin medir |
| `09-vacio.pdf` | 0 bytes | Error claro: «archivo vacío» | sin medir |
| `10-solo-cabecera.pdf` | Solo `%PDF-1.7` | Error claro: «incompleto» | sin medir |
| `11-no-es-pdf.pdf` | Texto plano con extensión .pdf | Error claro: «no es un PDF válido» | sin medir |
| `12-pagina-gigante.pdf` | Página de 100.000 × 100.000 puntos | Se rechaza o se limita la escala de renderizado; nunca intenta reservar un lienzo gigante | sin medir |

## Reglas que debe cumplir el motor ante todos estos casos

1. **Nunca se cuelga la pestaña.** Si un caso tarda más de 30 s en
   abrirse, es un fallo: hay que poner un tope de tiempo.
2. **Nunca se cae la página.** Un PDF malo da un mensaje, no una
   pantalla en blanco.
3. **El mensaje es en español y dice qué hacer** («prueba con otro
   PDF», «quítale la contraseña», …).
4. **No se reserva memoria según lo que el PDF declara** (conteo de
   páginas, `Length`, tamaño de página): se comprueba contra lo real
   antes de reservar.
5. **Nada de esto se sube a ningún servidor:** las pruebas corren en
   local, en el navegador.

## Cómo correr las pruebas

```bash
node web/tests/generate-hostile-pdfs.mjs   # regenera los fixtures
python3 -m http.server 8080 --directory web
# abre http://localhost:8080/tests/
```

La página intenta abrir cada fixture con el motor (y con pdf.js como
referencia para la vista previa) y muestra una tabla con
aprobado/fallido por caso. Los resultados se copian a esta tabla a
mano, con fecha, cuando se midan.
