/**
 * Preprocesado de imagen para OCR, en píxeles grises puros (sin dependencias):
 * enderezado fino (±5°), autocontraste con guarda por densidad de tinta,
 * binarización (umbral 150) y eliminación de líneas de tabla largas.
 *
 * Traducción de app/converters/extract.py (_binarized_copy, _remove_rules) y
 * app/converters/ocr.py (deskew_angle). Los umbrales se conservaron porque
 * están medidos en el backend Python (ver docs/METRICAS.md): la binarización
 * adaptativa y Otsu empeoran las cifras en fotos inclinadas, así que no se usan.
 */

const DESKEW_MAX_DEG = 5;
const DESKEW_STEP_DEG = 0.5;
const BINARIZE_THRESHOLD = 150;
const RULE_MIN_LENGTH_PX = 120; // a 300 dpi, como en Python

/** Gira una imagen gris `angleDeg` grados (positivo = antihorario, como PIL). Bilineal.
 * `fill` es el valor de los píxeles que entran por los bordes (255 = blanco). */
export function rotateGray(gray, width, height, angleDeg, fill = 255) {
  const rad = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const cx = (width - 1) / 2;
  const cy = (height - 1) / 2;
  const out = new Uint8Array(width * height).fill(fill);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const dx = x - cx;
      const dy = y - cy;
      // inversa de la rotación: de dónde viene este píxel
      const sx = cos * dx + sin * dy + cx;
      const sy = -sin * dx + cos * dy + cy;
      const x0 = Math.floor(sx);
      const y0 = Math.floor(sy);
      const fx = sx - x0;
      const fy = sy - y0;
      if (x0 < 0 || y0 < 0 || x0 + 1 >= width || y0 + 1 >= height) continue;
      const i00 = y0 * width + x0;
      const i10 = i00 + 1;
      const i01 = i00 + width;
      const i11 = i01 + 1;
      const top = gray[i00] * (1 - fx) + gray[i10] * fx;
      const bot = gray[i01] * (1 - fx) + gray[i11] * fx;
      out[y * width + x] = Math.round(top * (1 - fy) + bot * fy);
    }
  }
  return out;
}

/** Gira 90°/180°/270° (sentido horario) una imagen gris. Exacto, sin remuestreo. */
export function rotateGray90(gray, width, height, turns) {
  const t = ((turns % 4) + 4) % 4;
  if (t === 0) return { gray, width, height };
  if (t === 2) {
    const out = new Uint8Array(width * height);
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++) out[y * width + x] = gray[(height - 1 - y) * width + (width - 1 - x)];
    return { gray: out, width, height };
  }
  const out = new Uint8Array(width * height);
  if (t === 1) {
    // 90° horario: (x, y) -> (h-1-y, x)
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++) out[x * height + (height - 1 - y)] = gray[y * width + x];
    return { gray: out, width: height, height: width };
  }
  // 270° horario: (x, y) -> (y, w-1-x)
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) out[(width - 1 - x) * height + y] = gray[y * width + x];
  return { gray: out, width: height, height: width };
}

/**
 * Ángulo de corrección (grados) que endereza la imagen: el que maximiza la
 * varianza del perfil de proyección horizontal, entre -5° y +5° en pasos de 0,5°.
 * 0.0 si no hay suficiente texto para estimarlo.
 */
export function deskewAngle(gray, width, height) {
  const maxW = 800;
  const sw = Math.min(width, maxW);
  const sh = Math.max(1, Math.round((height * sw) / width));
  // Imagen de tinta (tinta=255, fondo=0), como en Python: al girarla el
  // relleno es 0, así que los bordes no inflan la varianza del perfil.
  const small = new Uint8Array(sw * sh);
  for (let y = 0; y < sh; y++) {
    const sy = Math.min(height - 1, Math.floor((y * height) / sh));
    for (let x = 0; x < sw; x++) {
      const sx = Math.min(width - 1, Math.floor((x * width) / sw));
      small[y * sw + x] = gray[sy * width + sx] < 128 ? 255 : 0;
    }
  }
  let blackCount = 0;
  for (let i = 0; i < small.length; i++) blackCount += small[i] > 0 ? 1 : 0;
  if (blackCount < 500) return 0.0;

  let bestAngle = 0.0;
  let bestScore = -1;
  for (let step = -10; step <= 10; step++) {
    const angle = step * DESKEW_STEP_DEG;
    const rotated = angle === 0 ? small : rotateGray(small, sw, sh, angle, 0);
    // varianza del perfil horizontal (suma por fila)
    let sum = 0;
    let sumSq = 0;
    for (let y = 0; y < sh; y++) {
      let row = 0;
      for (let x = 0; x < sw; x++) row += rotated[y * sw + x];
      sum += row;
      sumSq += row * row;
    }
    const mean = sum / sh;
    const score = sumSq / sh - mean * mean;
    if (score > bestScore) {
      bestScore = score;
      bestAngle = angle;
    }
  }
  return bestAngle;
}

/** Autocontraste con la guarda por densidad de tinta de Python (cutoff=1 solo si ≥1 % de píxeles oscuros). */
export function autocontrast(gray) {
  let min = 255;
  let max = 0;
  let dark = 0;
  for (let i = 0; i < gray.length; i++) {
    const v = gray[i];
    if (v < min) min = v;
    if (v > max) max = v;
    if (v < 150) dark++;
  }
  const blackFrac = dark / gray.length;
  const cutoff = blackFrac >= 0.01 ? 1 : 0;
  let lo = min;
  let hi = max;
  if (cutoff === 1) {
    // percentil 1 y 99 (aproximado por histograma)
    const hist = new Uint32Array(256);
    for (let i = 0; i < gray.length; i++) hist[gray[i]]++;
    let acc = 0;
    const p1 = gray.length * 0.01;
    const p99 = gray.length * 0.99;
    lo = 0;
    hi = 255;
    for (let v = 0; v < 256; v++) {
      acc += hist[v];
      if (lo === 0 && acc >= p1) lo = v;
      if (acc >= p99) {
        hi = v;
        break;
      }
    }
  }
  if (hi <= lo) return gray.slice();
  const out = new Uint8Array(gray.length);
  const scale = 255 / (hi - lo);
  for (let i = 0; i < gray.length; i++) {
    const v = Math.round((gray[i] - lo) * scale);
    out[i] = v < 0 ? 0 : v > 255 ? 255 : v;
  }
  return out;
}

/**
 * Borra líneas de tabla largas (horizontales y verticales de ≥120 px a 300 dpi).
 * Sin esto, Tesseract descarta o lee mal el texto que tocan las líneas.
 * Devuelve imagen binaria (0 = negro, 255 = blanco).
 */
export function removeRules(binary, width, height, length = RULE_MIN_LENGTH_PX) {
  const black = binary; // Uint8Array 0/255
  const hRun = new Uint8Array(width * height);
  const vRun = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    let run = 0;
    for (let x = 0; x < width; x++) {
      run = black[y * width + x] === 0 ? run + 1 : 0;
      if (run >= length) for (let k = 0; k < length; k++) hRun[y * width + x - k] = 1;
    }
  }
  for (let x = 0; x < width; x++) {
    let run = 0;
    for (let y = 0; y < height; y++) {
      run = black[y * width + x] === 0 ? run + 1 : 0;
      if (run >= length) for (let k = 0; k < length; k++) vRun[(y - k) * width + x] = 1;
    }
  }
  const out = new Uint8Array(width * height);
  for (let i = 0; i < width * height; i++) {
    out[i] = (hRun[i] || vRun[i]) && black[i] === 0 ? 255 : black[i];
  }
  return out;
}

/**
 * Pipeline completo: endereza, autocontraste, binariza y quita líneas.
 * Devuelve { gray: Uint8Array binaria (0/255), angle }.
 */
export function preprocessForOcr(gray, width, height) {
  const angle = deskewAngle(gray, width, height);
  let img = gray;
  if (Math.abs(angle) >= 0.5) img = rotateGray(img, width, height, angle);
  img = autocontrast(img);
  const bin = new Uint8Array(img.length);
  for (let i = 0; i < img.length; i++) bin[i] = img[i] < BINARIZE_THRESHOLD ? 0 : 255;
  return { gray: removeRules(bin, width, height), angle };
}
