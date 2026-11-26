# Despliegue gratis ($0): publicar la web estática en Vercel (o GitHub Pages)

Guía paso a paso para poner el convertidor en internet **sin pagar
nada**, pensada para alguien que no es programador. Cada paso dice qué
tienes que ver en la pantalla y qué comando copiar y pegar.

> **Cambio respecto a la versión anterior de esta guía:** antes este
> documento explicaba cómo desplegar el **servidor** en Oracle Cloud.
> Eso se mudó a `docs/SERVIDOR_OPCIONAL.md` (el servidor ya no es
> necesario: la conversión ocurre en el navegador). **Esta guía es
> solo para la web estática** (`web/`): archivos HTML, CSS y JavaScript
> que se sirven tal cual, sin servidor, sin claves y sin secretos.

**Lo que vas a publicar:** la carpeta `web/` del repositorio
(`index.html`, `excel.html`, `word.html`, `pptx.html`, `styles.css`,
`app.js`, `writers.js`, `engine.js`, `config.js`, `vendor/`,
`sw.js`…). No hay nada que instalar en el servidor ni variables de
entorno que configurar: la web no tiene claves. Si algún día activas
el servidor opcional, solo tendrás que poner su URL en
`web/config.js` (ver `docs/SERVIDOR_OPCIONAL.md`).

**Lo que necesitas antes de empezar:**

- [ ] Una cuenta de GitHub (gratis) con el repositorio
      `Joel06777/pdf-converter`.
- [ ] El repositorio en **público** antes de lanzar (obligatorio por
      la licencia AGPL-3.0; ver `docs/LICENCIAS.md`). Mientras sea
      privado, la web puede publicarse igual, pero no se puede ofrecer
      el servicio en abierto.
- [ ] Una cuenta de Vercel (gratis, plan Hobby) **o** usar GitHub
      Pages (ver opción B abajo). No necesitas tarjeta para ninguna de
      las dos.
- [ ] Un ordenador con terminal y conexión a internet.

## Los números del plan gratis (verificados el 26 nov 2026)

**Vercel Hobby** (plan gratuito). Fuentes: página de precios de
Vercel y sus directrices de uso razonable, leídas a través de
resúmenes verificados el 19–22 nov 2026 (ver «Qué quedó sin
verificar» al final: los números coinciden en varias fuentes
independientes, pero **confírmalos en
<https://vercel.com/pricing> antes de lanzar**, porque cambian sin
aviso):

| Recurso | Lo que incluye Hobby al mes |
|---|---|
| Transferencia de datos (lo que baja cada visitante) | **100 GB** |
| Peticiones a la CDN | **1 millón** |
| Despliegues | 100 al día, 200 proyectos |
| Funciones serverless | 1 millón de invocaciones (esta web **no usa ninguna**: es estática) |
| Dominios propios | HTTPS automático incluido |

**La condición importante de Hobby: solo uso personal y no
comercial.** Vercel lo define en sus directrices de uso razonable:
un sitio es comercial si sirve para ganar dinero alguien implicado
en él (cobrar a los visitantes, anuncios, vender un producto o
servicio, enlaces de afiliado como propósito principal, o que te
paguen por construirlo o alojarlo). Pedir donaciones no cuenta como
comercial. **Si el convertidor va a ganar dinero (por ejemplo,
vendiendo algo o con anuncios), Hobby no sirve: hace falta el plan
Pro (20 $/mes por puesto, según la página de precios).** Decide esto
antes de lanzar: no es un límite técnico que se pueda pagar aparte,
es una condición del plan.

**Qué pasa si se agota el límite:** en Hobby no se puede comprar más
uso. Cuando un recurso se agota, esa función queda parada hasta que
se renueva el periodo (en la mayoría de los casos, 30 días). Con
100 GB al mes, una web estática como esta (la primera visita baja
~1,1 MB de librerías y después casi nada, porque quedan en caché)
aguanta decenas de miles de visitas; el límite que antes se agota
suele ser la transferencia, no las peticiones.

**GitHub Pages** (opción B, también gratis). Fuente oficial:
<https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages>
(verificada el 26 nov 2026): disponible en repositorios **públicos**
con GitHub Free; un sitio por repositorio (o por cuenta, en el caso
de `<usuario>.github.io`); dominio propio con HTTPS. **Los límites
numéricos de GitHub Pages (tamaño del sitio, ancho de banda mensual,
despliegues por hora) no se verificaron en esta ronda** en la página
oficial de límites: consúltalos en la documentación de GitHub antes
de depender de ellos. GitHub Pages no admite cabeceras HTTP
personalizadas: la política de seguridad (CSP) de esta web va
entonces solo en la etiqueta `<meta>` de cada HTML (ya está puesta),
sin las cabeceras de `vercel.json`.

## Opción A — Publicar en Vercel (recomendado)

### Paso 1 — Preparar el proyecto en tu ordenador

1. Clona el repositorio (si aún no lo tienes en tu ordenador):
   ```bash
   git clone https://github.com/Joel06777/pdf-converter.git
   cd pdf-converter
   ```
2. Comprueba que la carpeta `web/` tiene lo necesario:
   ```bash
   ls web
   # Debes ver: index.html excel.html word.html pptx.html privacy.html
   # styles.css app.js writers.js engine.js config.js vercel.json sw.js
   # manifest.webmanifest favicon.svg vendor/ tests/ engine/
   ```
   `web/engine/` es el motor. Sus archivos generados (`index.js`,
   `dist/`, `vendor/mupdf/`) **no** están en el repositorio: se
   construyen con `npm run build` (ver paso 3). Si falta
   `web/engine/`, no pasa nada: la web se publica igual y funciona
   en modo de demostración (vista previa sí, conversión todavía no)
   hasta que el motor exista.

### Paso 2 — Crear la cuenta de Vercel

1. Entra en <https://vercel.com/signup> y crea la cuenta con tu
   cuenta de GitHub (**«Continue with GitHub»**). Así Vercel podrá
   leer tu repositorio.
2. **Qué debes ver:** al entrar en <https://vercel.com/dashboard>
   aparece tu panel vacío, con el botón **«Add New… → Project»**.

### Paso 3 — Crear el proyecto desde GitHub

1. En el panel, pulsa **«Add New…» → «Project»**.
2. En **«Import Git Repository»**, busca `Joel06777/pdf-converter`
   y pulsa **«Import»**.
3. En la pantalla de configuración del proyecto:
   - **Framework Preset:** elige **«Other»** (no es Next.js ni
     ningún framework: son archivos estáticos).
   - **Root Directory:** pulsa **«Edit»** y escribe `web`. Esto es
     lo importante: Vercel debe servir la carpeta `web/`, no la raíz
     del repositorio.
     **Qué debes ver:** «Root Directory: web».
   - **Build Command:** escribe `cd engine && npm ci && npm run build`.
     Esto construye el motor (`web/engine/index.js`, `dist/worker.js`,
     `vendor/mupdf/`) en cada despliegue; sin él, la web se publica en
     modo de demostración (vista previa sí, conversión no), porque
     esos archivos generados no están en el repositorio.
     **Qué debes ver:** «Build Command: cd engine && npm ci && npm run build».
   - **Node.js Version:** en **Settings → General → Node.js Version**
     elige **20.x** (el motor exige Node 20 o superior).
   - **Output Directory:** déjalo vacío (Vercel sirve los archivos
     tal cual).
   - **Environment Variables:** **ninguna**. Esta web no tiene
     claves ni secretos. Si ves una guía vieja que pide
     `CONVERTER_BACKEND_URL` o `CONVERTER_API_KEY`, es del
     `web-example/` antiguo con servidor: no aplica a `web/`.
4. Pulsa **«Deploy»** y espera. Tarda menos de un minuto.
   **Qué debes ver:** «Congratulations!» y una dirección como
   `https://pdf-converter-tu-usuario.vercel.app`.

### Paso 4 — Comprobar que la web funciona

1. Abre la dirección que te dio Vercel.
2. **Qué debes ver:** el título «Convertidor PDF a Word, Excel y
   PowerPoint», la zona de «Arrastra tu PDF aquí» y, en el pie,
   los enlaces «Código fuente» y «Política de privacidad».
3. Arrastra un PDF pequeño y comprueba que se ve la vista previa y
   que el botón «Convertir» produce el archivo (por ejemplo, una
   factura a Excel). Si el botón dice que el motor no está instalado,
   el build falló: revisa en Vercel → tu proyecto → **Deployments →
   el despliegue → Build Logs** que `npm run build` terminara sin
   error.
4. Comprueba la PWA: en el celular, el navegador debe ofrecer
   «Añadir a pantalla de inicio». Tras la primera visita, la página
   abre sin conexión.

### Paso 5 — Publicar cada cambio (despliegues automáticos)

Cada vez que subas un cambio a la rama `main` del repositorio,
Vercel publica la web nueva solo, en menos de un minuto. No hay que
hacer nada más. Para subir un cambio:

```bash
git add web/ docs/
git commit -m "Descripción del cambio"
git push origin main
```

**Ojo con la caché:** los archivos de `web/vendor/` llevan la
versión en el nombre y tienen caché larga (1 año): al actualizar una
librería, cambia el nombre del archivo (ya lo hace así) y la web
nueva se sirve sola. El Service Worker (`sw.js`) usa un nombre de
caché con versión (`pdf-converter-v1`): **sube ese número (`v2`,
`v3`…) en cada versión nueva de la web**, o los visitantes seguirán
viendo la vieja.

### Paso 6 — (Opcional) Poner tu propio dominio

1. En Vercel → tu proyecto → **Settings → Domains**, escribe tu
   dominio (por ejemplo, `convertidor.tudominio.com`) y pulsa **«Add»**.
2. Vercel te dirá qué registro DNS poner en tu proveedor de dominio
   (un registro `CNAME` que apunta a `cname.vercel-dns.com.`).
3. El certificado HTTPS lo emite Vercel solo, gratis.

### Paso 7 — (Opcional) Cambiar las librerías a jsDelivr

Por defecto las librerías se sirven desde tu propio sitio
(`web/vendor/`). Si prefieres que las sirva la CDN pública jsDelivr
(gratis, sin límite de ancho de banda según sus Términos de Uso
vigentes del 5 oct 2026), cambia **una línea** en `web/config.js`:

```js
vendorBase: "jsdelivr",
```

Y vuelve a desplegar (paso 5). No hay que tocar nada más: las
versiones y las huellas SRI son las mismas. El motor
(`web/engine/`) siempre se sirve desde tu sitio, nunca por CDN.
Detalle en `web/README.md`.

## Opción B — Publicar en GitHub Pages (alternativa genérica)

Si no quieres usar Vercel, GitHub Pages publica la misma carpeta
`web/` gratis, directamente desde el repositorio.

1. En GitHub, entra en tu repositorio → **Settings → Pages**.
2. En **«Build and deployment → Source»**, elige
   **«GitHub Actions»** (recomendado) o **«Deploy from a branch»**.
3. Si eliges «Deploy from a branch»: elige la rama `main` y la
   carpeta `/web` (si GitHub no te deja elegir subcarpeta, publica
   desde la raíz y mueve el contenido de `web/` a la raíz de una
   rama `gh-pages`).
   **Ojo:** con «Deploy from a branch» GitHub publica los archivos
   tal cual están en el repositorio, y los del motor (`index.js`,
   `dist/`, `vendor/mupdf/`) **no** están en el repositorio porque
   se generan con el build. Sin ellos la web queda en modo
   demostración. Para GitHub Pages usa **«GitHub Actions»** con un
   flujo que ejecute `cd web/engine && npm ci && npm run build`
   antes de publicar (el mismo comando que usa la CI de este
   repositorio), o construye el motor en tu ordenador y sube los
   archivos generados a la rama que publiques (no recomendado:
   son 14 MB y se desactualizan).
4. **Qué debes ver:** arriba de la pantalla de Pages aparece
   «Your site is live at
   `https://joel06777.github.io/pdf-converter/`».
5. **Diferencias con Vercel:** GitHub Pages no admite las cabeceras
   HTTP de `vercel.json` (CSP, caché larga, HSTS): la seguridad va
   solo en la etiqueta `<meta>` de cada HTML, que ya está puesta.
   La caché larga de `web/vendor/` no aplica: los archivos se sirven
   con la caché por defecto de GitHub. Todo lo demás (PWA, modo sin
   conexión, conversión en el navegador) funciona igual.

## Compresión y rendimiento (qué hace la plataforma por ti)

- **Brotli/gzip:** Vercel comprime los archivos automáticamente
  (Brotli cuando el navegador lo admite). No hay nada que configurar.
  En GitHub Pages la compresión la aplica GitHub; tampoco hay nada
  que configurar.
- **Carga diferida:** la web ya la hace sola: el motor se descarga
  al primer uso, cada librería de escritura solo cuando se convierte
  a ese formato, el ZIP solo cuando se pide, y los datos de idioma
  del OCR solo si hace falta (ver `docs/METRICAS.md`).
- **Caché larga con nombres con huella:** los archivos de
  `web/vendor/` llevan la versión en el nombre
  (`exceljs-4.4.0.min.js`) y `vercel.json` les da
  `Cache-Control: public, max-age=31536000, immutable`. Los HTML,
  CSS y JS propios tienen caché corta (1 hora) y el Service Worker
  se invalida con su número de versión. Medido el 26 nov 2026: la
  primera visita baja 4,75 MB con Brotli (16,13 MB sin comprimir)
  sin OCR, y 9,60 MB con Brotli (25,69 MB sin comprimir) si el PDF
  es un escaneado y hace falta el OCR; las siguientes, casi nada
  (el Service Worker guarda el motor). Detalle en `docs/METRICAS.md`.

## Qué quedó sin verificar

- **Vercel Hobby:** los números (100 GB/mes, 1 millón de peticiones)
  y la condición de uso no comercial se contrastaron con varias
  fuentes independientes que citan la página oficial de precios y
  las directrices de uso razonable (lecturas del 19–22 nov 2026),
  pero **no se leyó directamente la página oficial de Vercel en
  esta ronda**. Confirma en <https://vercel.com/pricing> y en
  <https://vercel.com/docs> antes de lanzar: los planes cambian sin
  aviso (Oracle, por ejemplo, recortó su plan gratis a la mitad en
  junio de 2026 sin anunciarlo).
- **GitHub Pages:** solo se verificó en la documentación oficial que
  es gratis en repositorios públicos con GitHub Free. Sus límites
  numéricos no se verificaron en esta ronda.
- **jsDelivr:** Términos de Uso verificados en el repositorio
  oficial (`github.com/jsdelivr/jsdelivr`, «Terms of Use»,
  vigente desde el 5 oct 2026): gratis para uso personal y
  comercial, sin límites de ancho de banda ni de peticiones; paquete
  npm ≤ 150 MB y archivo de GitHub ≤ 20 MB por defecto.
