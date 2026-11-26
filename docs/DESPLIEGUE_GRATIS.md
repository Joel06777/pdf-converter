# Despliegue gratis ($0): Oracle Cloud + DuckDNS + Caddy + Vercel

Guía paso a paso para poner el convertidor en internet **sin pagar nada**,
pensada para alguien que no es programador. Cada paso dice qué tienes que
ver en la pantalla y qué comando copiar y pegar. Si algo no se parece a lo
que dice aquí, para y pregunta: las pantallas de Oracle cambian y los
números del plan gratuito también.

**Lo que vas a montar:** la web sigue en Vercel (gratis, plan Hobby) y el
motor de conversión corre en un servidor gratis de Oracle Cloud, con un
nombre gratis de DuckDNS y HTTPS automático con Caddy.

**Lo que NO es esta guía:** no es el despliegue para 200 conversiones a la
vez. El plan gratis de Oracle da 2 CPU y 12 GB de memoria: de sobra para
empezar y para un uso normal (decenas de usuarios al día), pero las 200
conversiones simultáneas en hora pico son el objetivo de diseño con
hardware de pago, no con el plan gratis. En el plan gratis se levanta con
2 workers (cada uno convierte un archivo a la vez). Si el servicio crece,
se amplía el servidor y se paga solo por esa ampliación.

**Por qué no Hugging Face Spaces:** en 2026 las cuentas nuevas reciben
cuota 0 de CPU gratis y crear un Space que ejecute código (Gradio o Docker)
exige el plan PRO de pago, según reportes de usuarios y respuestas del
personal de Hugging Face en su propio foro. Por eso no se usa.

## Antes de empezar: lo que necesitas

- [ ] Una cuenta de correo (para Oracle y para DuckDNS).
- [ ] Una tarjeta (Oracle la pide para verificar la cuenta; no debería
      cobrarte nada mientras te mantengas dentro del plan Always Free —
      compruébalo en la pantalla de registro y no crees ningún recurso que
      diga «de pago»).
- [ ] Un ordenador con terminal (en Windows, usa la terminal de Ubuntu/WSL
      o Git Bash) y conexión a internet.
- [ ] Tu web ya desplegada en Vercel (o el proyecto `web-example/` listo).
- [ ] El repositorio `Joel06777/pdf-converter` (privado por ahora; para
      lanzar en abierto debe hacerse público, ver `docs/LICENCIAS.md`).

## Los números del plan gratis (verificados el 26 nov 2026)

Fuente oficial: página «Always Free Resources» de Oracle
(<https://docs.oracle.com/iaas/Content/FreeTier/resourceref.htm>),
contrastada con guías actualizadas de octubre–noviembre de 2026. Ojo: casi
todas las guías viejas dicen 4 CPU y 24 GB; **eso cambió en junio de 2026**.

| Recurso | Lo que incluye Always Free |
|---|---|
| Servidor ARM (Ampere A1, forma `VM.Standard.A1.Flex`) | 1.500 horas de OCPU + 9.000 horas de GB al mes, equivalentes a **2 OCPU y 12 GB de memoria** en total (un servidor de 2 OCPU/12 GB, o dos de 1 OCPU/6 GB) |
| Servidores AMD pequeños | Hasta 2 instancias `VM.Standard.E2.1.Micro` (1/8 OCPU, 1 GB cada una) |
| Disco (almacenamiento en bloque) | **200 GB** en total en la tenencia, incluido el disco de arranque (mínimo 47 GB por disco de arranque) |
| Salida de datos a internet | **10 TB al mes** |
| Región | **Solo tu región principal («home region»)**, que eliges al registrarte y **no se puede cambiar después** |

**Tres riesgos que tienes que conocer antes de elegir:**

1. **Si el servidor está sin uso 7 días, Oracle puede reclamarlo
   (borrarlo).** La regla oficial: si durante 7 días el uso de CPU (percentil
   95), de red y —solo en A1— de memoria están todos por debajo del 20 %,
   la instancia se considera inactiva y puede ser reclamada. Un servicio
   con visitas normales supera esos umbrales; un servicio sin ninguna visita
   en una semana, no. Varias guías indican que pasar la cuenta a
   «Pay As You Go» (seguiría siendo $0 dentro de los límites Always Free)
   elimina este riesgo; eso no se ha verificado en la documentación oficial
   en esta ronda, consúltalo en la FAQ de Oracle antes de decidir.
   **No uses trucos de «carga falsa»** (programas que consumen CPU a
   propósito para parecer activo): varias guías advierten de que es una zona
   gris en los términos de Oracle y puede suspender la cuenta.
2. **Error «sin capacidad» («Out of capacity»).** Las instancias A1 gratis
   se agotan a menudo en las regiones populares. No es un problema de tu
   cuenta: es falta de capacidad. Qué hacer (ver paso 1.5).
3. **La región principal no se cambia.** Elige la más cercana a tus
   usuarios. Para usuarios en Ecuador, las regiones de EE. UU. (Ashburn,
   Phoenix o San José) son las habituales; dentro de Oracle verás la lista
   completa al registrarte.

## Paso 1 — Crear la cuenta de Oracle y el servidor

### 1.1 Registrarse

1. Entra en <https://signup.cloud.oracle.com/> y crea la cuenta con tu
   correo. Sigue los pasos de verificación que te pida (correo, teléfono y
   tarjeta para verificar la identidad).
2. **Elige la región principal («Home Region») con cuidado**: no se puede
   cambiar después. Escoge la más cercana a tus usuarios.
3. Cuando te pregunte por el tipo de cuenta, quédate en el plan gratuito
   («Always Free»). No actives recursos de pago.

> **Qué debes ver:** al entrar en la consola de Oracle (<https://cloud.oracle.com>)
> arriba a la derecha aparece tu región principal. Si no coincide con la
> que elegiste, no sigas: estás en otra región y los recursos gratis solo
> existen en la principal.

### 1.2 Crear la instancia (el servidor)

1. En la consola de Oracle, ve a **Compute → Instances → Create instance**.
2. Ponle un nombre, por ejemplo `convertidor-pdf`.
3. En **Image and shape → Image**, pulsa **Change image** y elige
   **Canonical Ubuntu**, versión **24.04**, arquitectura **aarch64 (ARM)**.
   Lo que debes ver: «Canonical Ubuntu 24.04 LTS (aarch64)».
4. En **Shape**, pulsa **Change shape → Ampere → `VM.Standard.A1.Flex`**
   y ajusta los deslizadores a **2 OCPU y 12 GB de memoria**.
   Lo que debes ver: «VM.Standard.A1.Flex» con 2 OCPU y 12 GB.
5. En **Boot volume**, deja el tamaño en **50 GB** (el mínimo es 47 GB y el
   total gratis es 200 GB; con 50 GB hay sitio de sobra para Docker, las
   imágenes y los trabajos temporales).
6. En **Add SSH keys**, elige **Generate a key pair** y descarga las dos
   claves que te da Oracle (`id_rsa` y `id_rsa.pub`). **Guárdalas en un
   lugar seguro**: sin la clave privada no podrás entrar al servidor.
   En Windows, guárdalas en `C:\Users\<tu-usuario>\.ssh\`.
7. En **Networking**, deja la red por defecto (VCN) y marca **Assign a
   public IPv4 address**.
8. Pulsa **Create** y espera a que el estado pase a **Running**. Anota la
   **dirección IP pública** que aparece en la ficha de la instancia
   (por ejemplo, `129.146.XX.XX`).

### 1.3 Entrar al servidor por primera vez

En tu terminal (con la clave privada descargada):

```bash
chmod 400 /ruta/a/tu-clave-privada.key
ssh -i /ruta/a/tu-clave-privada.key ubuntu@TU-IP-PUBLICA
```

Lo que debes ver: el saludo de Ubuntu y un prompt como
`ubuntu@convertidor-pdf:~$`. Ya estás dentro del servidor.

### 1.4 Si al crearla sale «Out of capacity» / «sin capacidad»

Es el problema más común y no significa que hiciste algo mal. Prueba en
este orden:

1. **Reintenta en otra hora** (madrugada o fin de semana de la región, hay
   menos gente pidiendo).
2. **Cambia de zona de disponibilidad** (Availability Domain) dentro de la
   misma región: en el formulario de creación hay un desplegable «Availability
   domain» con AD-1, AD-2, AD-3. Prueba otra.
3. **Pide una forma más pequeña**: 1 OCPU y 6 GB de memoria en vez de
   2 OCPU y 12 GB. El servicio funciona igual con 1 OCPU para empezar
   (con 1 worker en vez de 2); luego puedes crear otra instancia o
   redimensionar.
4. Como último recurso temporal, crea una `VM.Standard.E2.1.Micro` (AMD,
   casi siempre hay capacidad): solo tiene 1 GB de memoria, así que sirve
   para probar, pero **no** para uso real con este servicio (los workers
   tienen límite de 2 GB cada uno en `docker-compose.yml` y no caben).

> No crees varias cuentas para cambiar de región: Oracle lo prohíbe en sus
> términos y puede suspenderlas.

## Paso 2 — Abrir los puertos 80 y 443 (dos cortafuegos, no uno)

Aquí es donde más gente se atasca: Oracle tiene **dos** cortafuegos y hay
que abrir los puertos en los dos. Si abres solo uno, la web no cargará.

### 2.1 Lista de seguridad de Oracle (en la consola web)

1. En la consola de Oracle, ve a **Networking → Virtual Cloud Networks**,
   entra en tu VCN y luego en **Security Lists → Default Security List**.
2. Pulsa **Add Ingress Rules** y añade estas tres reglas (una por una):
   - Puerto **22** (SSH), origen `0.0.0.0/0`, protocolo TCP. (Suele existir
     ya; si existe, no la dupliques.)
   - Puerto **80** (HTTP), origen `0.0.0.0/0`, protocolo TCP.
   - Puerto **443** (HTTPS), origen `0.0.0.0/0`, protocolo TCP.
3. Guarda. Lo que debes ver: tres reglas de entrada con los puertos 22, 80
   y 443.

### 2.2 Cortafuegos del propio servidor (iptables)

La imagen de Ubuntu de Oracle trae reglas de iptables que solo permiten el
puerto 22. Hay que abrir el 80 y el 443 dentro del servidor. Conéctate por
SSH y ejecuta:

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -L INPUT -n --line-numbers | head -20
```

Lo que debes ver: en la lista aparecen reglas ACCEPT para los puertos 80 y
443.

Para que estas reglas **sobrevivan a un reinicio** del servidor:

```bash
sudo apt-get update && sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save
```

> Si al instalar `iptables-persistent` te pregunta si guardar las reglas
> actuales, responde que **sí** en las dos preguntas.

Comprueba que el puerto 80 responde (desde tu propio ordenador, no desde el
servidor):

```bash
curl -v http://TU-IP-PUBLICA/ --max-time 10
```

De momento dará error de conexión o «connection refused» porque aún no hay
nada sirviendo: eso es normal. Lo importante es que no diga «timeout»
(eso indicaría que el cortafuegos sigue cerrado).

## Paso 3 — Instalar Docker y Docker Compose

Dentro del servidor, por SSH, copia y pega estos comandos **en orden**.
Instalan Docker desde el repositorio oficial de Docker para Ubuntu 24.04
(ARM64). Tarda unos minutos.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Añade tu usuario al grupo `docker` para no tener que escribir `sudo` antes
de cada comando de Docker, y **cierra la sesión SSH y vuelve a entrar**
para que el cambio tenga efecto:

```bash
sudo usermod -aG docker $USER
exit
```

Vuelve a entrar por SSH y comprueba:

```bash
docker --version
docker compose version
```

Lo que debes ver: algo como `Docker version 28.x.x` y
`Docker Compose version v2.x.x`. Docker descargará automáticamente la
versión ARM64 de cada imagen oficial que usa el proyecto
(`python:3.12-slim`, `redis:7-alpine`, `caddy:2`).

## Paso 4 — Dominio gratis con DuckDNS y HTTPS automático con Caddy

### 4.1 Crear el subdominio en DuckDNS

1. Entra en <https://www.duckdns.org/> e inicia sesión (puedes hacerlo con
   tu cuenta de GitHub, Google o similar).
2. En «sub domains», escribe un nombre, por ejemplo
   `convertidor-pdf-fabian`, y pulsa **add domain**. Tu dominio será
   `convertidor-pdf-fabian.duckdns.org`.
3. En la misma página verás tu **token** (una cadena larga de letras y
   números). Cópialo y guárdalo: es la contraseña que actualiza tu dominio.
   **No lo publiques ni lo subas a GitHub.**
4. Apunta el subdominio a la IP pública de tu servidor Oracle: en la misma
   página de DuckDNS, escribe la IP en el campo «current ip» de tu dominio
   y pulsa **update ip**.

DuckDNS es gratis, permite hasta 5 subdominios por cuenta y no caduca por
falta de uso según sus propias condiciones. Como la IP de Oracle es fija
(no cambia al reiniciar), la actualización es casi siempre de una sola vez;
aun así, el script de instalación (paso 8) deja programada una actualización
automática cada 5 minutos por si la IP cambiara alguna vez.

Comprueba que el dominio ya apunta a tu servidor (desde tu ordenador):

```bash
nslookup convertidor-pdf-fabian.duckdns.org
```

Lo que debes ver: la IP pública de tu servidor Oracle.

### 4.2 HTTPS automático con Caddy

Caddy es el servidor que recibe las visitas por HTTPS y las pasa al
convertidor. Consigue el certificado gratis de Let's Encrypt **solo**,
sin que tengas que hacer nada más, siempre que el dominio ya apunte al
servidor (paso 4.1) y los puertos 80 y 443 estén abiertos (paso 2).

En el servidor, dentro de la carpeta del proyecto, crea el archivo
`Caddyfile` con este contenido (cambia el dominio por el tuyo):

```caddyfile
convertidor-pdf-fabian.duckdns.org {
    reverse_proxy localhost:8000
}
```

Caddy se levanta como un contenedor Docker aparte (tal como se hace en
`docs/DESPLIEGUE.md`):

```bash
docker run -d --name caddy --network host --restart unless-stopped \
  -v $PWD/Caddyfile:/etc/caddy/Caddyfile caddy:2
```

Lo que debes ver: `docker ps` muestra el contenedor `caddy` en estado
`Up`. Al cabo de un minuto, entrar en
`https://convertidor-pdf-fabian.duckdns.org/health` debe mostrar
`{"ok":true,...}` (si el convertidor ya está levantado; si aún no, sigue
al paso 5 y vuelve a probar).

## Paso 5 — El archivo `.env` de producción (las claves secretas)

### 5.1 Generar las claves

**Nunca inventes las claves a mano ni reutilices una de otro proyecto.**
Genera cada una con este comando (cópialo y pégalo en el servidor; cada
vez que lo ejecutas sale una distinta):

```bash
openssl rand -hex 32
```

Repite el comando **dos veces** y apunta los dos resultados en un lugar
seguro (por ejemplo, en tu gestor de contraseñas): el primero será
`API_KEY` y el segundo `DOWNLOAD_SECRET`.

### 5.2 Crear el `.env`

En el servidor, dentro de la carpeta del proyecto:

```bash
cp .env.example .env
nano .env
```

Edita estos valores (borra los que vienen de ejemplo y pega los tuyos):

```env
STORAGE_DIR=/data/jobs
REDIS_URL=redis://redis:6379/0
MAX_UPLOAD_MB=50
MAX_PAGES=200
JOB_TTL_MINUTES=60
ALLOWED_ORIGINS=https://tu-sitio.vercel.app
API_KEY=pega-aqui-la-primera-clave-generada
DOWNLOAD_SECRET=pega-aqui-la-segunda-clave-generada
RATE_LIMIT_PER_HOUR=60
OCR_LANG=spa+eng
TASK_TIME_LIMIT=600
```

- `ALLOWED_ORIGINS`: pon **el dominio exacto de tu web en Vercel**, por
  ejemplo `https://tu-sitio.vercel.app`. Solo esa web podrá llamar al
  convertidor desde el navegador.
- `API_KEY`: la clave que la web de Vercel enviará en cada petición
  (cabecera `X-API-Key`). Sin ella, cualquiera podría usar tu servidor.
- `DOWNLOAD_SECRET`: firma los enlaces de descarga, que caducan a los
  15 minutos.
- El resto de valores son los de `.env.example` y no hace falta tocarlos.

> **⚠️ `UPLOAD_SECRET` NO existe en esta versión del código.**
> En el encargo original de esta guía se pedía una variable llamada
> `UPLOAD_SECRET` (y en Vercel, la misma), pero **no hay ninguna variable
> con ese nombre** en `app/config.py`, en `.env.example` ni en
> `web-example/api/convert.js` (verificado el 26 nov 2026). No la crees
> esperando que proteja las subidas: no haría nada. La subida se protege
> con `API_KEY` (que solo conoce el servidor de Vercel, nunca el navegador)
> y con el límite de 60 conversiones por IP y hora. Si en el futuro se
> añade un token de subida al código, se documentará aquí.

**Cómo guardar las claves sin subirlas a GitHub:**

- El archivo `.env` **ya está en `.gitignore`**: Git lo ignora y nunca se
  sube al repositorio. Compruébalo con `git status`: el `.env` no debe
  aparecer.
- No pegues las claves en chats, capturas de pantalla, issues de GitHub ni
  correos.
- Si una clave se filtra, genera otra con `openssl rand -hex 32`, cámbiala
  en el `.env` del servidor **y** en Vercel (paso 6), y reinicia con
  `docker compose up -d`.

## Paso 6 — Variables en Vercel

En el panel de Vercel, entra en tu proyecto → **Settings → Environment
Variables** y añade estas dos (para los entornos Production, Preview y
Development):

| Variable | Valor |
|---|---|
| `CONVERTER_BACKEND_URL` | `https://convertidor-pdf-fabian.duckdns.org` (tu dominio, sin `/` al final) |
| `CONVERTER_API_KEY` | El **mismo valor** de `API_KEY` que pusiste en el `.env` del servidor |

Después de añadirlas, **vuelve a desplegar** la web en Vercel (Deployments →
⋯ → Redeploy) para que las variables tengan efecto.

> **⚠️ `UPLOAD_SECRET` tampoco existe en Vercel.** No hay ninguna variable
> con ese nombre en `web-example/api/convert.js`: el proxy de Vercel solo
> lee `CONVERTER_BACKEND_URL` y `CONVERTER_API_KEY`. No añadas una variable
> `UPLOAD_SECRET` en Vercel: no la leería nada. Ver la nota del paso 5.2.

**Límite importante de Vercel Hobby (verificado en la documentación de
Vercel, vigente en 2026):** las funciones serverless del plan Hobby solo
aceptan cuerpos de petición de hasta **4,5 MB**. Un PDF mayor de 4,5 MB que
pase por el proxy de Vercel (`web-example/api/convert.js`) será rechazado
con error 413. Por eso el proyecto ya lo advierte en el propio
`convert.js`: para PDFs de hasta 50 MB, la web debe subir el archivo
**directo al backend** (con URL firmada) en vez de pasar por la función
serverless. Ese cambio en la web aún no está hecho: con el proxy actual,
los PDF de más de 4,5 MB no se pueden subir desde la web. Tenlo en cuenta
antes de anunciar «hasta 50 MB».

## Paso 7 — Levantar el servicio, actualizar y ver los logs

### 7.1 Primera puesta en marcha

En el servidor, dentro de la carpeta del proyecto:

```bash
docker compose up -d --build
docker compose ps
```

Lo que debes ver: los servicios `api`, `worker`, `beat` y `redis` en
estado `Up` o `running`. En el plan gratis no escales los workers: con
`docker compose up -d` tal cual ya arranca 1 worker (concurrencia 2, ver
`docker-compose.yml`). Si quieres 2 workers, añade `--scale worker=2`,
pero vigila la memoria (cada worker tiene un límite de 2 GB).

Comprueba la salud del servicio:

```bash
curl https://convertidor-pdf-fabian.duckdns.org/health
curl https://convertidor-pdf-fabian.duckdns.org/metrics | head -20
```

Lo que debes ver: `{"ok":true,"redis":true,"disco_libre_mb":...}` y varias
líneas de métricas.

### 7.2 Actualizar cuando haya cambios en el código

```bash
cd ~/pdf-converter
git pull
docker compose up -d --build
docker compose ps
```

Si solo cambió la documentación (archivos `.md`), no hace falta
reconstruir: basta con `git pull`.

### 7.3 Ver los logs (cuando algo falla)

```bash
docker compose logs -f --tail=100 api
docker compose logs -f --tail=100 worker
```

Pulsa `Ctrl+C` para salir. Los logs **no contienen el contenido de los
documentos**: solo el identificador del trabajo, el destino, el estado y
la duración (ver `docs/PRIVACIDAD.md`). Si un trabajo da error, el mensaje
de error en español aparece en el estado del trabajo
(`GET /api/v1/jobs/{id}`).

### 7.4 Reiniciar todo

```bash
docker compose restart
```

## Paso 8 — Plan B: reconstruir todo en otro servidor en menos de 30 minutos

Si Oracle reclama la instancia, si la borras por error o si quieres
cambiar de servidor, no hay que repetir esta guía a mano. El script
`scripts/bootstrap.sh` hace todo lo de los pasos 2.2 a 7 en un solo
comando, en un servidor Ubuntu 24.04 nuevo:

```bash
bash scripts/bootstrap.sh convertidor-pdf-fabian.duckdns.org
```

El script es **idempotente en lo posible**: si lo ejecutas dos veces, no
rompe nada — reutiliza el `.env` si ya existe (no regenera las claves),
actualiza el repositorio si ya está clonado y vuelve a levantar los
contenedores. Lo que hace, en orden:

1. Instala Docker y Docker Compose si faltan.
2. Clona el repositorio (o hace `git pull` si ya existe) en
   `~/pdf-converter`.
3. Genera el `.env` si no existe (con `API_KEY` y `DOWNLOAD_SECRET`
   aleatorios) y te muestra dónde quedó para que lo copies.
4. Crea el `Caddyfile` con tu dominio si no existe.
5. Levanta el servicio con `docker compose up -d --build` y el contenedor
   de Caddy.
6. Si le pasas el token de DuckDNS, programa la actualización automática
   del dominio cada 5 minutos:
   `DUCKDNS_TOKEN=tu-token bash scripts/bootstrap.sh tu-dominio.duckdns.org`

**No hay datos de usuarios que respaldar**: los PDF originales se borran
al terminar cada conversión y los resultados se borran a los 60 minutos
(ver `docs/PRIVACIDAD.md`). Lo único que hay que guardar fuera del
servidor son: las claves del `.env`, el token de DuckDNS y la clave SSH.
Guárdalos en tu gestor de contraseñas. Si pierdes el `.env`, genera claves
nuevas (paso 5.1) y actualiza Vercel (paso 6).

**Antes de lanzar el script en un servidor nuevo, recuerda**: la instancia
hay que crearla a mano en la consola de Oracle (paso 1) y los puertos
80/443 hay que abrirlos en la lista de seguridad de Oracle (paso 2.1).
El script no puede hacer esas dos cosas porque necesitan la consola web.

## Alternativa casera: un PC o portátil viejo encendido 24/7

Si no quieres depender de Oracle, puedes correr el mismo Docker en un
ordenador viejo en casa. Pros y contras honestos:

**Pros:**

- No dependes de Oracle: nadie te reclama el servidor por inactividad ni
  te da error «sin capacidad».
- El hardware ya lo tienes: $0.
- Control total: puedes apagarlo, moverlo y ampliar el disco cuando quieras.

**Contras:**

- **Electricidad 24/7**: un portátil viejo consume poco, pero un PC de
  sobremesa encendido siempre se nota en la factura de luz. Calcula
  cuánto consume el tuyo antes de decidir.
- **Internet de casa**: necesitas que el puerto 80/443 llegue a ese
  ordenador. Opciones: abrir los puertos en tu router (cada router es
  distinto; busca «abrir puertos» + el modelo de tu router) o usar un túnel
  (por ejemplo, Cloudflare Tunnel, gratis, sin abrir puertos). Abrir
  puertos expone tu red de casa: hazlo solo si sabes lo que abres y
  mantén el sistema actualizado.
- **IP que cambia**: la IP pública de casa suele cambiar. DuckDNS la
  actualiza sola con el programador del paso 4.1, pero si se cae internet
  en casa, se cae el servicio.
- **Un dominio propio cuesta**: un dominio `.com` cuesta unos $10–15 al
  año en un registrador. Los subdominios de DuckDNS (`*.duckdns.org`)
  **son gratis**, así que para empezar no necesitas comprar dominio.
- **Ruido, calor y fiabilidad**: un equipo viejo puede fallar sin avisar.
  Ten el Plan B (paso 8) listo para reconstruir en Oracle si el equipo
  casero muere.

**Recomendación:** empieza en Oracle (gratis y sin tocar tu red de casa).
La opción casera solo compensa si ya tienes el equipo encendido por otro
motivo.

## Opcional: protección contra robots con Cloudflare Turnstile

> **No implementado en el código.** Esto es una opción para el futuro, no
> un paso de esta guía. No hay ningún código de Turnstile en el repositorio.

Si el servicio recibe abuso (muchas subidas automáticas), una opción es
Cloudflare Turnstile, un reto anti-robots sin puzles. Según la página de
planes de Cloudflare, consultada por terceros en noviembre de 2026,
Turnstile sigue siendo **gratis: retos ilimitados, hasta 20 widgets por
cuenta** (fuente: <https://antibot.dev/vendors/turnstile/>, que revisó la
página de precios de Cloudflare el 13 de noviembre de 2026; ver también
<https://www.dreamhost.com/blog/captcha-alternative/>). Para usarlo habría
que añadir el widget en la web y verificar el token en el servidor: es
trabajo pendiente, no lo hagas en este despliegue.

## Lo que NO se pudo verificar en esta ronda

- **Docker en ARM64 de Oracle**: no había Docker disponible en este equipo
  para probar el despliegue de principio a fin. Los comandos de esta guía
  son los oficiales de Docker para Ubuntu 24.04 y de Oracle; la primera
  instalación real debe hacerse siguiendo la guía y anotando cualquier
  diferencia.
- **El script `scripts/bootstrap.sh`**: validado con `bash -n` (sintaxis
  correcta). `shellcheck` **no está instalado** en este equipo, así que no
  se pudo pasar. Tampoco se pudo ejecutar el script entero (necesita un
  servidor Ubuntu nuevo con acceso a internet y a Oracle).
- **Los números de Oracle**: verificados en la documentación oficial y en
  guías de octubre–noviembre de 2026, pero Oracle cambia los límites sin
  avisar (ya lo hizo en junio de 2026). Antes de crear la instancia,
  comprueba la página «Always Free Resources» de Oracle.
- **El límite de 4,5 MB de Vercel**: verificado en la documentación de
  Vercel citada por varias fuentes de 2026; el propio `web-example/api/convert.js`
  ya lo advierte en un comentario.
- **Que Pay As You Go elimine el riesgo de reclamación por inactividad**:
  lo afirman varias guías, pero no se verificó en la documentación oficial
  en esta ronda.
- **El precio de la electricidad y la apertura de puertos del router** en
  la alternativa casera: depende de tu equipo y de tu proveedor; no se
  puede dar una cifra.

## Fuentes

- Oracle, «Always Free Resources» (documentación oficial):
  <https://docs.oracle.com/iaas/Content/FreeTier/resourceref.htm>
- Guías actualizadas sobre el recorte de junio de 2026 (2 OCPU / 12 GB) y
  la regla de inactividad de 7 días:
  <https://dev.to/travenwest/what-you-can-self-host-on-oracle-cloud-free-tier-2026-3gfd>,
  <https://github.com/simien/cldenv/blob/HEAD/guides/oracle_cloud_setup.md>,
  <https://www.computerandmobile.com/oracle-cloud-free-tier-vps/>
- Vercel, límites de funciones (4,5 MB por cuerpo de petición; 300 s en
  Hobby con Fluid compute): <https://vercel.com/docs/functions/limitations>
  (citada por varias fuentes en 2026).
- Hugging Face Spaces, cuota 0 de CPU en cuentas nuevas (2026):
  <https://discuss.huggingface.co/t/free-cpu-basic-quota-is-0-on-new-account/180764/1>
- DuckDNS: <https://www.duckdns.org/>
- Cloudflare Turnstile (gratis, verificado por terceros en nov 2026):
  <https://antibot.dev/vendors/turnstile/>
