/**
 * Extracción del modelo de una página PDF con MuPDF.js (mupdf 1.28.6):
 * texto con estilo y posición por carácter, rellenos, líneas, imágenes y
 * gráficos vectoriales rasterizados.
 *
 * Es la traducción de app/converters/extract.py (PyMuPDF) a la API de MuPDF.js:
 * - Texto: `page.toStructuredText()` + walker `onChar` (posición por carácter,
 *   fuente, tamaño, negrita, cursiva y color). Verificado en la sonda:
 *   5.447 caracteres, 178 líneas en el documento de referencia, con el `$`
 *   en su propia posición (x=423,125).
 * - Vectores e imágenes: `page.run()` con un `Device` propio (`fillPath`,
 *   `strokePath`, `fillImage`). Las rutas con curvas (logotipos) se rasterizan
 *   como imágenes, igual que en Python.
 * - OCR: solo si la página es un escaneo sin texto; lo hace `ocr.js`
 *   (tesseract.js) sobre un render gris a 300 dpi preprocesado.
 */
import { ConversionError } from "./errors.js";
// El módulo MuPDF.js se inyecta por parámetro (opts.mupdf): en Node es el
// paquete "mupdf" y en el navegador es el mismo módulo cargado por URL desde
// los estáticos del sitio. Así el motor no depende de un empaquetador.
import { checkPageDimensions, checkPageModel, LIMITS } from "./limits.js";
import { encodePng } from "./png.js";

// Una imagen que cubre más de este porcentaje de la página se considera "fondo escaneado".
const SCAN_COVERAGE = 0.8;
// Por debajo de esta cantidad de caracteres, una página con imagen grande se considera escaneada.
const MIN_TEXT_CHARS = 20;

const FONT_MAP = {
  gotham: "Arial",
  helvetica: "Arial",
  arialmt: "Arial",
  couriernew: "Courier New",
  courier: "Courier New",
  timesnewroman: "Times New Roman",
  times: "Times New Roman",
};

export function cleanFontName(name) {
  const base0 = String(name ?? "").split("+").pop();
  if (!base0 || base0.toLowerCase().startsWith("cidfont") || /^[A-Za-z]{0,2}\d+$/.test(base0)) {
    return "Calibri";
  }
  let base = base0.split(/[-,]/)[0];
  base = base.replace(/(MT|PS)$/, "").trim();
  return FONT_MAP[base.replace(/ /g, "").toLowerCase()] || base || "Calibri";
}

function colorToHex(color) {
  if (!color) return null;
  const comps = Array.from(color);
  let r;
  let g;
  let b;
  if (comps.length === 1) {
    r = g = b = comps[0];
  } else if (comps.length === 3) {
    [r, g, b] = comps;
  } else if (comps.length === 4) {
    // CMYK
    const [c, m, y, k] = comps;
    r = 1 - Math.min(1, c + k);
    g = 1 - Math.min(1, m + k);
    b = 1 - Math.min(1, y + k);
  } else {
    return null;
  }
  const hex = (v) => Math.max(0, Math.min(255, Math.round(v * 255))).toString(16).padStart(2, "0").toUpperCase();
  return `${hex(r)}${hex(g)}${hex(b)}`;
}

function isWhite(hexColor) {
  return ["FFFFFF", "FEFEFE", "FDFDFD"].includes(String(hexColor ?? "").toUpperCase());
}

/** Aplica la matriz [a,b,c,d,e,f] a un punto. */
function applyMatrix(m, x, y) {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

/** Caja envolvente de un quad MuPDF [ulx,uly, urx,ury, llx,lly, lrx,lry]. */
function quadBox(quad) {
  const xs = [quad[0], quad[2], quad[4], quad[6]];
  const ys = [quad[1], quad[3], quad[5], quad[7]];
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/**
 * Recorre una ruta y devuelve sus tramos ya transformados por la CTM.
 * @returns {{ segments: Array<[number,number,number,number]>, hasCurve: boolean, closed: boolean }}
 */
function walkPath(path, ctm) {
  const segments = [];
  let hasCurve = false;
  let closed = false;
  let cur = null;
  let start = null;
  path.walk({
    moveTo(x, y) {
      cur = applyMatrix(ctm, x, y);
      start = cur;
    },
    lineTo(x, y) {
      const p = applyMatrix(ctm, x, y);
      if (cur) segments.push([cur[0], cur[1], p[0], p[1]]);
      cur = p;
    },
    curveTo() {
      hasCurve = true;
    },
    closePath() {
      closed = true;
      if (cur && start) segments.push([cur[0], cur[1], start[0], start[1]]);
      cur = start;
    },
  });
  return { segments, hasCurve, closed };
}

/** ¿Es el tramo un rectángulo de 4 lados (tolerancia 0,5 pt)? */
function rectFromSegments(segments) {
  if (segments.length !== 4) return null;
  const xs = new Set();
  const ys = new Set();
  for (const [x0, y0, x1, y1] of segments) {
    xs.add(+x0.toFixed(1));
    xs.add(+x1.toFixed(1));
    ys.add(+y0.toFixed(1));
    ys.add(+y1.toFixed(1));
  }
  if (xs.size !== 2 || ys.size !== 2) return null;
  const xa = [...xs].sort((a, b) => a - b);
  const ya = [...ys].sort((a, b) => a - b);
  return { x0: xa[0], y0: ya[0], x1: xa[1], y1: ya[1] };
}

function mergeRegions(regions) {
  const merged = [];
  for (const r of regions) {
    let target = null;
    for (const m of merged) {
      if (m.x0 <= r.x1 && r.x0 <= m.x1 && m.y0 <= r.y1 && r.y0 <= m.y1) {
        target = m;
        break;
      }
    }
    if (target) {
      target.x0 = Math.min(target.x0, r.x0);
      target.y0 = Math.min(target.y0, r.y0);
      target.x1 = Math.max(target.x1, r.x1);
      target.y1 = Math.max(target.y1, r.y1);
    } else {
      merged.push({ ...r });
    }
  }
  return merged;
}

/**
 * Extrae el modelo de una página.
 * @param {object} doc documento MuPDF
 * @param {number} pageIndex
 * @param {object} opts { ocr: boolean, ocrLang: string, ocrRunner?: (pngBytes, widthPt, heightPt) => Promise<words>, onOcrProgress?: fn }
 * @returns {Promise<PageModel>}
 */
export async function extractPage(doc, pageIndex, opts = {}) {
  const { ocr = true, ocrLang = "spa+eng", ocrRunner = null, onOcrProgress = null, mupdf } = opts;
  if (!mupdf) throw new ConversionError("Motor MuPDF no cargado.", "conversion_fallida");
  const page = doc.loadPage(pageIndex);
  const [bx0, by0, bx1, by1] = page.getBounds();
  const width = bx1 - bx0;
  const height = by1 - by0;
  checkPageDimensions(width, height);
  const model = {
    width,
    height,
    spans: [],
    fills: [],
    lines: [],
    images: [],
    scanned: false,
    ocrUsed: false,
    ocrConfidences: [],
    deskewDegrees: 0,
    rotation: 0,
    nativeChars: 0,
  };

  // --- texto por carácter
  const t0 = Date.now();
  const stext = page.toStructuredText("preserve-whitespace");
  let currentDir = [1, 0];
  let currentLine = null;
  const textLines = [];
  stext.walk({
    beginLine(_bbox, _wmode, dir) {
      if (dir) currentDir = [dir[0], dir[1]];
      currentLine = { dir: [...currentDir], chars: [] };
      textLines.push(currentLine);
    },
    onChar(c, _origin, font, size, quad, color) {
      const [x0, y0, x1, y1] = quadBox(quad);
      const fontName = font.getName();
      const low = fontName.toLowerCase();
      const ch = {
        c,
        x0,
        y0,
        x1,
        y1,
        font: cleanFontName(fontName),
        size: Math.round(size * 10) / 10,
        bold: font.isBold() || low.includes("bold") || low.includes("black"),
        italic: font.isItalic() || low.includes("italic") || low.includes("oblique"),
        color: colorToHex(color) ?? "000000",
        rotation: Math.round((Math.atan2(currentDir[1], currentDir[0]) * 180) / Math.PI * 10) / 10,
      };
      if (currentLine) currentLine.chars.push(ch);
      else textLines.push({ dir: [...currentDir], chars: [ch] });
    },
    endLine() {
      currentLine = null;
    },
  });
  const chars = textLines.flatMap((l) => l.chars);
  if (chars.length > LIMITS.maxCharsPerPage) {
    throw new ConversionError("La página tiene demasiado texto para procesarla de forma segura.", "limite_excedido");
  }
  model.spans = splitCharsIntoSpans(textLines);
  if (Date.now() - t0 > LIMITS.maxMsPerPage) {
    throw new ConversionError("La extracción de texto de esta página tardó demasiado.", "limite_excedido");
  }

  // --- vectores e imágenes (Device propio)
  const graphicRegions = [];
  const device = new mupdf.Device({
    fillPath(path, _evenOdd, ctm, _cs, color, _alpha) {
      const fill = colorToHex(color);
      const { segments, hasCurve } = walkPath(path, ctm);
      const rect = rectFromSegments(segments);
      if (hasCurve || (!rect && segments.length > 4)) {
        const [x0, y0, x1, y1] = path.getBounds(null, ctm);
        graphicRegions.push({ x0, y0, x1, y1 });
        return;
      }
      if (rect) {
        const w = rect.x1 - rect.x0;
        const h = rect.y1 - rect.y0;
        if (fill && !isWhite(fill)) {
          if (Math.min(w, h) <= 1.6) {
            // rectángulo finísimo = línea
            if (w >= h) {
              model.lines.push({ orient: "h", pos: (rect.y0 + rect.y1) / 2, a: rect.x0, b: rect.x1, width: Math.max(h, 0.5), color: fill });
            } else {
              model.lines.push({ orient: "v", pos: (rect.x0 + rect.x1) / 2, a: rect.y0, b: rect.y1, width: Math.max(w, 0.5), color: fill });
            }
          } else {
            model.fills.push({ ...rect, color: fill });
          }
        }
        return;
      }
      // polilínea rellena sin curvas y no rectangular: se trata como gráfico
      const [x0, y0, x1, y1] = path.getBounds(null, ctm);
      graphicRegions.push({ x0, y0, x1, y1 });
    },
    strokePath(path, stroke, ctm, _cs, color, _alpha) {
      const strokeColor = colorToHex(color) ?? "000000";
      const width = stroke.getLineWidth() || 0.5;
      const { segments, hasCurve } = walkPath(path, ctm);
      if (hasCurve || segments.length > 40) {
        // Trazo complejo (firma, garabato): se rasteriza la zona, como en Python.
        const [x0, y0, x1, y1] = path.getBounds(stroke, ctm);
        graphicRegions.push({ x0, y0, x1, y1 });
        return;
      }
      for (const [x0, y0, x1, y1] of segments) {
        if (Math.abs(y0 - y1) < 0.8) {
          model.lines.push({ orient: "h", pos: (y0 + y1) / 2, a: Math.min(x0, x1), b: Math.max(x0, x1), width, color: strokeColor });
        } else if (Math.abs(x0 - x1) < 0.8) {
          model.lines.push({ orient: "v", pos: (x0 + x1) / 2, a: Math.min(y0, y1), b: Math.max(y0, y1), width, color: strokeColor });
        }
      }
    },
    fillImage(image, ctm, _alpha) {
      const corners = [
        applyMatrix(ctm, 0, 0),
        applyMatrix(ctm, 1, 0),
        applyMatrix(ctm, 0, 1),
        applyMatrix(ctm, 1, 1),
      ];
      const xs = corners.map((p) => p[0]);
      const ys = corners.map((p) => p[1]);
      const x0 = Math.min(...xs);
      const y0 = Math.min(...ys);
      const x1 = Math.max(...xs);
      const y1 = Math.max(...ys);
      const png = imageToPng(mupdf, image);
      if (png) {
        model.images.push({
          x0,
          y0,
          x1,
          y1,
          png,
          fullPage: false,
          pixelWidth: image.getWidth(),
          pixelHeight: image.getHeight(),
        });
      }
    },
    fillImageMask(_image, ctm, _cs, _color, _alpha) {
      // Máscara de imagen (p. ej. logotipo 1 bit): se rasteriza la zona.
      const corners = [applyMatrix(ctm, 0, 0), applyMatrix(ctm, 1, 1)];
      graphicRegions.push({
        x0: Math.min(corners[0][0], corners[1][0]),
        y0: Math.min(corners[0][1], corners[1][1]),
        x1: Math.max(corners[0][0], corners[1][0]),
        y1: Math.max(corners[0][1], corners[1][1]),
      });
    },
  });
  page.run(device, mupdf.Matrix.identity);
  device.close();

  // --- gráficos vectoriales complejos (logotipos con curvas) se rasterizan
  for (const region of mergeRegions(graphicRegions)) {
    const rx0 = Math.max(bx0, region.x0);
    const ry0 = Math.max(by0, region.y0);
    const rx1 = Math.min(bx1, region.x1);
    const ry1 = Math.min(by1, region.y1);
    if (rx1 - rx0 < 2 || ry1 - ry0 < 2) continue;
    const png = renderRegionPng(mupdf, page, rx0, ry0, rx1, ry1);
    if (png) {
      model.images.push({ x0: rx0, y0: ry0, x1: rx1, y1: ry1, png, fullPage: false, pixelWidth: 0, pixelHeight: 0 });
    }
  }

  // marcar imágenes de página completa
  const pageArea = width * height;
  for (const img of model.images) {
    img.fullPage = (img.x1 - img.x0) * (img.y1 - img.y0) >= SCAN_COVERAGE * pageArea;
  }

  // --- escaneo: OCR si no hay texto nativo
  const hasFullImage = model.images.some((i) => i.fullPage);
  const nativeChars = model.spans.reduce((n, s) => n + s.text.trim().length, 0);
  model.nativeChars = nativeChars;
  if (hasFullImage && nativeChars < MIN_TEXT_CHARS) {
    model.scanned = true;
    if (ocr) {
      if (!ocrRunner) {
        throw new ConversionError(
          "Esta página es una imagen escaneada y el OCR no está disponible en este entorno.",
          "ocr_no_disponible",
        );
      }
      const ocrResult = await runOcrOnPage(mupdf, page, model, ocrLang, ocrRunner, onOcrProgress);
      if (ocrResult) {
        model.spans = ocrResult.spans;
        model.ocrConfidences = ocrResult.confidences;
        model.ocrUsed = true;
        model.deskewDegrees = ocrResult.angle;
      }
    }
  } else if (hasFullImage) {
    // PDF escaneado al que ya se le hizo OCR (texto invisible sobre la imagen)
    model.scanned = true;
  }

  // El mapa de confianza solo conserva palabras que quedaron en el texto extraído.
  if (model.ocrConfidences.length) {
    const tokens = new Set(model.spans.flatMap((s) => s.text.split(/\s+/)).map((t) => t.toLowerCase()));
    model.ocrConfidences = model.ocrConfidences.filter((w) => tokens.has(w.text.toLowerCase()));
  }

  checkPageModel(model);
  return model;
}

/** Extrae una imagen MuPDF como PNG, componiendo la máscara de transparencia si la hay. */
function imageToPng(mupdf, image) {
  try {
    const mask = image.getMask();
    if (!mask) {
      return image.toPixmap().asPNG();
    }
    const pix = image.toPixmap();
    const maskPix = mask.toPixmap();
    const w = pix.getWidth();
    const h = pix.getHeight();
    const n = pix.getNumberOfComponents();
    const px = pix.getPixels();
    const mp = maskPix.getPixels();
    if (w !== maskPix.getWidth() || h !== maskPix.getHeight()) return pix.asPNG();
    const rgba = new Uint8Array(w * h * 4);
    for (let i = 0; i < w * h; i++) {
      const a = mp[i];
      if (n >= 3) {
        rgba[i * 4] = px[i * n];
        rgba[i * 4 + 1] = px[i * n + 1];
        rgba[i * 4 + 2] = px[i * n + 2];
      } else {
        const g = px[i * n];
        rgba[i * 4] = g;
        rgba[i * 4 + 1] = g;
        rgba[i * 4 + 2] = g;
      }
      rgba[i * 4 + 3] = a;
    }
    return encodePng(w, h, rgba, 6);
  } catch {
    return null;
  }
}

/** Renderiza una región de la página a 200 dpi y la devuelve como PNG RGB. */
function renderRegionPng(mupdf, page, x0, y0, x1, y1) {
  try {
    const dpi = 200;
    const scale = dpi / 72;
    const pix = page.toPixmap(mupdf.Matrix.scale(scale, scale), mupdf.ColorSpace.DeviceRGB, false);
    const w = pix.getWidth();
    const h = pix.getHeight();
    const px = pix.getPixels();
    const n = pix.getNumberOfComponents();
    const px0 = Math.max(0, Math.floor(x0 * scale));
    const py0 = Math.max(0, Math.floor(y0 * scale));
    const px1 = Math.min(w, Math.ceil(x1 * scale));
    const py1 = Math.min(h, Math.ceil(y1 * scale));
    const rw = px1 - px0;
    const rh = py1 - py0;
    if (rw < 1 || rh < 1) return null;
    const rgb = new Uint8Array(rw * rh * 3);
    for (let y = 0; y < rh; y++) {
      for (let x = 0; x < rw; x++) {
        const si = ((py0 + y) * w + (px0 + x)) * n;
        const di = (y * rw + x) * 3;
        rgb[di] = px[si];
        rgb[di + 1] = px[si + 1];
        rgb[di + 2] = px[si + 2];
      }
    }
    return encodePng(rw, rh, rgb, 2);
  } catch {
    return null;
  }
}

/**
 * OCR de una página escaneada: render gris a 300 dpi, preprocesado y tesseract.js.
 * El `ocrRunner` lo inyecta el llamador (convert.js) para no acoplar el motor a
 * la creación del worker de Tesseract.
 *
 * Las cajas de Tesseract vienen en píxeles de la imagen PROCESADA (tras el
 * enderezado y los giros de 90°): aquí se invierten esas transformaciones y se
 * escalan a puntos de página, para que los spans queden en el mismo espacio
 * que el resto del modelo.
 */
async function runOcrOnPage(mupdf, page, model, ocrLang, ocrRunner, onOcrProgress) {
  const { preprocessForOcr, rotateGray90 } = await import("./preprocess.js");
  const { encodePng: encode } = await import("./png.js");
  const scale = 300 / 72;
  const pix = page.toPixmap(mupdf.Matrix.scale(scale, scale), mupdf.ColorSpace.DeviceGray, false);
  const renderW = pix.getWidth();
  const renderH = pix.getHeight();
  let width = renderW;
  let height = renderH;
  let gray = pix.getPixels();
  // Páginas giradas 90°/270° (fotos de celular de lado): el render de MuPDF
  // sale en el espacio rotado, con el texto de lado. Se gira la imagen para
  // leerla; las cajas se devuelven luego a su sitio (ver abajo).
  const transform = page.getTransform();
  const pageAngle = Math.round((Math.atan2(transform[1], transform[0]) * 180) / Math.PI);
  // Giros de 90° en sentido horario para enderezar el texto. Medido: con
  // /Rotate 90 el giro correcto es 3 (90° antihorario); con 270 es 1.
  let turns = 0;
  if (pageAngle === 90 || pageAngle === -270) turns = 3;
  else if (pageAngle === 270 || pageAngle === -90) turns = 1;
  else if (pageAngle === 180 || pageAngle === -180) turns = 2;
  if (turns) {
    const rotated = rotateGray90(gray, width, height, turns);
    gray = rotated.gray;
    width = rotated.width;
    height = rotated.height;
  }
  const { gray: bin, angle } = preprocessForOcr(gray, width, height);
  const png = encode(width, height, bin, 0);
  const wordsPx = await ocrRunner(png);
  if (!wordsPx || wordsPx.length === 0) return null;
  const words = wordsPx.map((w) => {
    const box = unrotateBox(w, width, height, angle, turns);
    return {
      ...w,
      x0: (box.x0 * model.width) / renderW,
      y0: (box.y0 * model.height) / renderH,
      x1: (box.x1 * model.width) / renderW,
      y1: (box.y1 * model.height) / renderH,
    };
  });
  if (onOcrProgress) onOcrProgress(words.length);
  return { spans: wordsToSpans(words), confidences: words, angle };
}

/** Invierte el enderezado (`angle`) y el giro de 90° (`turns`) de una caja. */
function unrotateBox(box, width, height, angle, turns) {
  // 1. Invertir el enderezado: la caja está en la imagen girada `angle` por
  // rotateGray; el muestreo inverso usa la misma fórmula con el mismo ángulo.
  const cx = (width - 1) / 2;
  const cy = (height - 1) / 2;
  const rad = (angle * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const unskew = ([x, y]) => {
    const dx = x - cx;
    const dy = y - cy;
    return [cos * dx + sin * dy + cx, -sin * dx + cos * dy + cy];
  };
  let corners = [
    [box.x0, box.y0],
    [box.x1, box.y0],
    [box.x0, box.y1],
    [box.x1, box.y1],
  ].map(unskew);
  // 2. Invertir el giro de 90° (coordenadas de la imagen girada -> original).
  if (turns) {
    const w2 = width;
    const h2 = height;
    corners = corners.map(([x, y]) => {
      if (turns === 1) return [y, w2 - 1 - x];
      if (turns === 2) return [w2 - 1 - x, h2 - 1 - y];
      return [h2 - 1 - y, x];
    });
  }
  const xs = corners.map((p) => p[0]);
  const ys = corners.map((p) => p[1]);
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
}

/**
 * Convierte palabras de OCR ({text, x0, y0, x1, y1, conf} en puntos) en spans,
 * partiendo por huecos grandes como hace _split_span en Python.
 */
function wordsToSpans(words) {
  // Restos de líneas de tabla leídos como "|", "_" o "¦": se descartan, como
  // hace Python (solo quedan fragmentos con letras, cifras o moneda).
  const kept = words.filter((w) => /[\w$€£%]/u.test(w.text));
  const spans = [];
  // Agrupar por línea (centro y con tolerancia de 45 % del alto).
  const ordered = [...kept].sort((a, b) => (a.y0 + a.y1) / 2 - (b.y0 + b.y1) / 2 || a.x0 - b.x0);
  const lines = [];
  for (const w of ordered) {
    const cy = (w.y0 + w.y1) / 2;
    const h = Math.max(6, w.y1 - w.y0);
    const tol = Math.max(2, 0.45 * h);
    const line = lines.find((l) => Math.abs(cy - l.cy) <= tol);
    if (line) {
      line.words.push(w);
      line.cy = line.words.reduce((s, x) => s + (x.y0 + x.y1) / 2, 0) / line.words.length;
    } else {
      lines.push({ cy, words: [w] });
    }
  }
  for (const line of lines) {
    const ws = line.words.sort((a, b) => a.x0 - b.x0);
    let cur = null;
    for (const w of ws) {
      const size = Math.max(6, w.y1 - w.y0);
      if (cur && w.x0 - cur.x1 < 0.7 * size) {
        cur.text += ` ${w.text}`;
        cur.x1 = Math.max(cur.x1, w.x1);
        cur.y0 = Math.min(cur.y0, w.y0);
        cur.y1 = Math.max(cur.y1, w.y1);
      } else {
        cur = {
          text: w.text,
          x0: w.x0,
          y0: w.y0,
          x1: w.x1,
          y1: w.y1,
          font: "Calibri",
          size: Math.round(size * 10) / 10,
          bold: false,
          italic: false,
          color: "000000",
          rotation: 0,
        };
        spans.push(cur);
      }
    }
  }
  return spans;
}

/**
 * Parte los caracteres de cada línea en spans: cambia el span cuando cambia la
 * fuente/estilo o cuando entre dos caracteres no-espacio hay un hueco grande
 * (> 0,9 × tamaño). Es _split_span de Python, aplicado sobre los caracteres
 * del walker de MuPDF.js (la separación "$" / cifra vive aquí).
 * @param {Array<{chars: Array}>} textLines líneas del walker de MuPDF.js
 */
function splitCharsIntoSpans(textLines) {
  const spans = [];
  for (const line of textLines) {
    const ordered = [...line.chars].sort((a, b) => a.x0 - b.x0);
    let parts = [[]];
    for (const ch of ordered) {
      if (ch.c === " " || ch.c === "\t") {
        parts[parts.length - 1].push(ch);
        continue;
      }
      const cur = parts[parts.length - 1];
      const last = [...cur].reverse().find((c) => c.c !== " " && c.c !== "\t");
      const sameStyle =
        last &&
        last.font === ch.font &&
        last.size === ch.size &&
        last.bold === ch.bold &&
        last.italic === ch.italic &&
        last.color === ch.color;
      if (last && (!sameStyle || ch.x0 - last.x1 > 0.9 * ch.size)) {
        parts.push([]);
      }
      parts[parts.length - 1].push(ch);
    }
    for (const part of parts) {
      const visible = part.filter((c) => c.c !== " " && c.c !== "\t");
      if (!visible.length) continue;
      const first = visible[0];
      spans.push({
        text: part.map((c) => c.c).join("").trim(),
        x0: Math.min(...visible.map((c) => c.x0)),
        y0: Math.min(...visible.map((c) => c.y0)),
        x1: Math.max(...visible.map((c) => c.x1)),
        y1: Math.max(...visible.map((c) => c.y1)),
        font: first.font,
        size: first.size,
        bold: first.bold,
        italic: first.italic,
        color: first.color,
        rotation: first.rotation,
      });
    }
  }
  return spans;
}

/** Agrupa spans en filas visuales y une fragmentos contiguos (group_rows de Python). */
export function groupRows(spans) {
  if (!spans.length) return [];
  const ordered = [...spans].sort((a, b) => (a.y0 + a.y1) / 2 - (b.y0 + b.y1) / 2 || a.x0 - b.x0);
  const clusters = [];
  const centers = [];
  for (const sp of ordered) {
    const cy = (sp.y0 + sp.y1) / 2;
    const tol = Math.max(2.0, 0.45 * sp.size);
    if (clusters.length && Math.abs(cy - centers[centers.length - 1]) <= tol) {
      clusters[clusters.length - 1].push(sp);
      centers[centers.length - 1] =
        clusters[clusters.length - 1].reduce((s, x) => s + (x.y0 + x.y1) / 2, 0) / clusters[clusters.length - 1].length;
    } else {
      clusters.push([sp]);
      centers.push(cy);
    }
  }
  const rows = [];
  for (const cluster of clusters) {
    cluster.sort((a, b) => a.x0 - b.x0);
    const segs = [];
    for (const sp of cluster) {
      const last = segs[segs.length - 1];
      if (last && sp.x0 - last.x1 < 0.7 * sp.size && !isLoneCurrency(last.text)) {
        last.text += ` ${sp.text}`;
        last.x1 = Math.max(last.x1, sp.x1);
        last.y0 = Math.min(last.y0, sp.y0);
        last.y1 = Math.max(last.y1, sp.y1);
      } else {
        segs.push({ ...sp });
      }
    }
    rows.push({ segments: segs, y0: Math.min(...segs.map((s) => s.y0)), y1: Math.max(...segs.map((s) => s.y1)) });
  }
  return rows;
}

function isLoneCurrency(text) {
  return ["$", "US$", "€", "£", "S/", "S/."].includes(String(text ?? "").trim());
}
