"""Extracción del modelo de una página PDF: texto con estilo, rellenos, líneas e imágenes.

Todo se hace con PyMuPDF (motor propio, sin servicios externos). El mismo modelo
alimenta a los conversores de Excel y PowerPoint, así que la fidelidad se mejora en un
solo lugar.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from io import BytesIO

import pymupdf

from .ocr import deskew_angle, word_confidences

# Una imagen que cubre más de este porcentaje de la página se considera "fondo escaneado".
SCAN_COVERAGE = 0.80
# Por debajo de esta cantidad de caracteres, una página con imagen grande se considera escaneada.
MIN_TEXT_CHARS = 20


class ConversionCancelled(Exception):
    """El usuario canceló el trabajo (ver POST /api/v1/jobs/{id}/cancel)."""


@dataclass
class Span:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font: str = "Calibri"
    size: float = 10.0
    bold: bool = False
    italic: bool = False
    color: str = "000000"
    rotation: float = 0.0  # grados del texto (0 = horizontal; 90/-90 = vertical)

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Fill:
    x0: float
    y0: float
    x1: float
    y1: float
    color: str


@dataclass
class Line:
    orient: str  # "h" o "v"
    pos: float  # y si es horizontal, x si es vertical
    a: float  # inicio sobre el eje de la línea
    b: float  # fin
    width: float
    color: str


@dataclass
class ImageBox:
    x0: float
    y0: float
    x1: float
    y1: float
    png: bytes
    full_page: bool = False


@dataclass
class PageModel:
    width: float
    height: float
    spans: list[Span] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    images: list[ImageBox] = field(default_factory=list)
    scanned: bool = False
    ocr_used: bool = False
    # Confianza del OCR por palabra: [{'text','x0','y0','x1','y1' (puntos), 'conf'}].
    ocr_confidences: list[dict] = field(default_factory=list)
    deskew_degrees: float = 0.0  # ángulo corregido al enderezar la página escaneada


# ----------------------------------------------------------------------------- utilidades

def _hex(color) -> str | None:
    """Convierte colores de PyMuPDF (tuplas 0-1) a 'RRGGBB'."""
    if color is None:
        return None
    if isinstance(color, (int, float)):
        color = (color,)
    if len(color) == 1:
        r = g = b = color[0]
    elif len(color) == 3:
        r, g, b = color
    elif len(color) == 4:  # CMYK
        c, m, y, k = color
        r, g, b = (1 - min(1, c + k), 1 - min(1, m + k), 1 - min(1, y + k))
    else:
        return None
    return "{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v * 255))) for v in (r, g, b)))


def _is_white(hexcolor: str) -> bool:
    return hexcolor.upper() in ("FFFFFF", "FEFEFE", "FDFDFD")


_FONT_MAP = {
    "gotham": "Arial",
    "helvetica": "Arial",
    "arialmt": "Arial",
    "couriernew": "Courier New",
    "courier": "Courier New",
    "timesnewroman": "Times New Roman",
    "times": "Times New Roman",
}


def clean_font_name(name: str) -> str:
    """'ABCDEF+Calibri-Bold' -> 'Calibri'. Fuentes sin nombre real (CIDFont) -> Calibri."""
    name = name.split("+")[-1]
    if not name or name.lower().startswith("cidfont") or re.fullmatch(r"[A-Za-z]{0,2}\d+", name):
        return "Calibri"
    base = re.split(r"[-,]", name)[0]
    base = re.sub(r"(MT|PS)$", "", base).strip()
    return _FONT_MAP.get(base.replace(" ", "").lower(), base or "Calibri")


def _pixmap_png(doc: pymupdf.Document, xref: int) -> bytes | None:
    """Extrae una imagen incrustada como PNG, conservando la transparencia."""
    try:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace is None or pix.colorspace.n != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        info = doc.extract_image(xref) or {}
        smask = info.get("smask") or 0
        if smask and not pix.alpha:
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
        return pix.tobytes("png")
    except Exception:
        return None


# ----------------------------------------------------------------------------- extracción

def extract_page(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    ocr: bool = True,
    ocr_lang: str = "spa+eng",
) -> PageModel:
    rect = page.rect
    model = PageModel(width=rect.width, height=rect.height)
    page_area = rect.width * rect.height

    # --- imágenes
    for info in page.get_image_info(xrefs=True):
        bbox = pymupdf.Rect(info["bbox"]) & rect
        if bbox.is_empty:
            continue
        png = _pixmap_png(doc, info.get("xref", 0)) if info.get("xref") else None
        if png is None:
            png = page.get_pixmap(clip=bbox, dpi=200).tobytes("png")
        full = bbox.width * bbox.height >= SCAN_COVERAGE * page_area
        model.images.append(ImageBox(bbox.x0, bbox.y0, bbox.x1, bbox.y1, png, full))

    has_full_image = any(i.full_page for i in model.images)
    native_chars = len(page.get_text().strip())

    # --- texto (con OCR propio si la página es un escaneo sin capa de texto)
    textpage = None
    ocr_page = page
    if has_full_image and native_chars < MIN_TEXT_CHARS:
        model.scanned = True
        if ocr:
            try:
                ocr_page, png_bytes, model.deskew_degrees = _binarized_copy(page)
                textpage = ocr_page.get_textpage_ocr(language=ocr_lang, dpi=300, full=True)
                model.ocr_used = True
                # Mapa de confianza por palabra (coordenadas de píxel -> puntos).
                img_w, img_h = _png_size(png_bytes)
                scale_x = rect.width / max(1, img_w)
                scale_y = rect.height / max(1, img_h)
                model.ocr_confidences = [
                    {"text": w["text"], "x0": w["x0"] * scale_x, "y0": w["y0"] * scale_y,
                     "x1": w["x1"] * scale_x, "y1": w["y1"] * scale_y, "conf": w["conf"]}
                    for w in word_confidences(png_bytes, ocr_lang)
                ]
            except Exception:
                textpage, ocr_page = None, page
    elif has_full_image:
        # PDF escaneado al que ya se le hizo OCR (texto invisible sobre la imagen)
        model.scanned = True

    data = ocr_page.get_text("rawdict", textpage=textpage) if textpage else page.get_text("rawdict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            # Dirección del texto: (1,0) horizontal; (0,1)/(0,-1) vertical; etc.
            direction = line.get("dir", (1.0, 0.0)) or (1.0, 0.0)
            rotation = round(math.degrees(math.atan2(direction[1], direction[0])), 1)
            for sp in line.get("spans", []):
                font = sp.get("font", "")
                flags = sp.get("flags", 0)
                low = font.lower()
                size = round(sp.get("size", 10.0), 1)
                style = dict(
                    font=clean_font_name(font),
                    size=size,
                    bold=bool(flags & 16) or "bold" in low or "black" in low,
                    italic=bool(flags & 2) or "italic" in low or "oblique" in low,
                    color="{:06X}".format(sp.get("color", 0)),
                )
                for text, x0, y0, x1, y1 in _split_span(sp.get("chars", []), size):
                    if model.ocr_used and not re.search(r"[\w$€£%]", text):
                        continue  # restos de líneas leídos como "|", "_" o "¦"
                    model.spans.append(Span(text=text, x0=x0, y0=y0, x1=x1, y1=y1, rotation=rotation, **style))

    # Corrección del símbolo Nº mal leído por el OCR (solo cuando hubo OCR:
    # el texto nativo nunca se toca). Va antes del filtro de confianzas para
    # que el mapa de confianza use ya el texto corregido.
    if model.ocr_used:
        for sp in model.spans:
            sp.text = _fix_ocr_numero(sp.text)
        for w in model.ocr_confidences:
            w["text"] = _fix_ocr_numero(w["text"])

    # El mapa de confianza viene de una segunda pasada de Tesseract: solo se
    # conservan las palabras que realmente quedaron en el texto extraído, para
    # no advertir sobre fragmentos que el conversor ya descartó.
    if model.ocr_confidences:
        tokens = {t.casefold() for s in model.spans for t in s.text.split()}
        model.ocr_confidences = [w for w in model.ocr_confidences if w["text"].casefold() in tokens]

    # --- vectores: rellenos y líneas
    graphic_regions: list[pymupdf.Rect] = []
    for d in page.get_drawings():
        fill = _hex(d.get("fill"))
        stroke = _hex(d.get("color"))
        width = d.get("width") or 0.5
        items = d.get("items", [])
        if any(it[0] == "c" for it in items) or len(items) > 40:
            graphic_regions.append(pymupdf.Rect(d["rect"]))
            continue
        for it in items:
            kind = it[0]
            if kind in ("re", "qu"):
                r = it[1] if kind == "re" else it[1].rect
                w, h = r.width, r.height
                if fill and not _is_white(fill):
                    if min(w, h) <= 1.6:  # rectángulo finísimo = línea
                        if w >= h:
                            model.lines.append(Line("h", (r.y0 + r.y1) / 2, r.x0, r.x1, max(h, 0.5), fill))
                        else:
                            model.lines.append(Line("v", (r.x0 + r.x1) / 2, r.y0, r.y1, max(w, 0.5), fill))
                    else:
                        model.fills.append(Fill(r.x0, r.y0, r.x1, r.y1, fill))
                if stroke and d.get("type") in ("s", "fs"):
                    c = stroke
                    model.lines.append(Line("h", r.y0, r.x0, r.x1, width, c))
                    model.lines.append(Line("h", r.y1, r.x0, r.x1, width, c))
                    model.lines.append(Line("v", r.x0, r.y0, r.y1, width, c))
                    model.lines.append(Line("v", r.x1, r.y0, r.y1, width, c))
            elif kind == "l" and stroke:
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 0.8:
                    model.lines.append(Line("h", (p1.y + p2.y) / 2, min(p1.x, p2.x), max(p1.x, p2.x), width, stroke))
                elif abs(p1.x - p2.x) < 0.8:
                    model.lines.append(Line("v", (p1.x + p2.x) / 2, min(p1.y, p2.y), max(p1.y, p2.y), width, stroke))

    # Los gráficos vectoriales complejos (logotipos dibujados con curvas) se rasterizan.
    for region in _merge_regions(graphic_regions):
        region = region & rect
        if region.is_empty or region.width < 2 or region.height < 2:
            continue
        png = page.get_pixmap(clip=region, dpi=200).tobytes("png")
        model.images.append(ImageBox(region.x0, region.y0, region.x1, region.y1, png))

    return model


def _long_runs(black, length: int):
    """Máscara de píxeles negros que forman tramos horizontales de al menos `length` píxeles."""
    import numpy as np

    cs = np.pad(np.cumsum(black, axis=1, dtype=np.int32), ((0, 0), (1, 0)))
    full = (cs[:, length:] - cs[:, :-length]) == length  # ventanas totalmente negras
    starts = np.pad(full.astype(np.int32), ((0, 0), (0, length)))
    cs2 = np.pad(np.cumsum(starts, axis=1), ((0, 0), (length, 0)))
    covered = (cs2[:, length:] - cs2[:, :-length]) > 0
    return covered[:, : black.shape[1]] & black


def _remove_rules(img):
    """Borra líneas de tabla largas (horizontales y verticales). Si tocan el texto, Tesseract
    lo descarta o lo lee mal; sin las líneas el texto queda aislado."""
    import numpy as np
    from PIL import Image

    black = np.asarray(img) < 128
    h = _long_runs(black, 120)
    v = _long_runs(black.T, 120).T
    out = np.where(h | v, 255, np.asarray(img)).astype("uint8")
    return Image.fromarray(out, "L")


def _png_size(png_bytes: bytes) -> tuple[int, int]:
    """Dimensiones en píxeles de un PNG en memoria."""
    from PIL import Image

    with Image.open(BytesIO(png_bytes)) as img:
        return img.size


def _binarized_copy(page: pymupdf.Page) -> tuple[pymupdf.Page, bytes, float]:
    """Copia de la página en blanco y negro puro, enderezada.

    Tesseract falla con texto sobre rellenos de color (barras verdes, sellos);
    al binarizar, el texto oscuro queda sobre blanco. Antes de binarizar se
    estima el ángulo de inclinación (fotos de celular, escaneos torcidos) y se
    gira la imagen para enderezarla. Devuelve (página, png_bytes, ángulo).
    """
    from io import BytesIO

    from PIL import Image, ImageOps

    pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    angle = deskew_angle(img)
    if abs(angle) >= 0.5:
        # BICUBIC (no NEAREST): el remuestreo por vecino degrada el texto y el OCR.
        img = img.rotate(angle, fillcolor=255, resample=Image.BICUBIC)
    # autocontrast: estira el contraste, pero con un guarda para páginas con
    # muy poco texto. Con cutoff=1, en páginas con <1 % de píxeles oscuros el
    # percentil 1 cae en un gris claro y TODO por debajo se vuelve negro
    # (medido: los píxeles negros se triplicaban y el texto salía duplicado
    # e ilegible). Con cutoff=0 eso no pasa, pero en fotos inclinadas el
    # engrosado leve de cutoff=1 ayuda a leer dígitos finos tras el giro
    # (medido: la cantidad "5" se perdía con cutoff=0). Por eso cutoff=1
    # solo cuando hay al menos 1 % de píxeles oscuros, que es justo el
    # percentil que recorta: en ese caso lo es un gris oscuro y el texto
    # queda intacto. cutoff=0 sigue estirando min/max (texto gris sobre
    # fondo gris), solo sin recortar.
    import numpy as np

    black_frac = float((np.asarray(img) < 150).mean())
    cutoff = 1 if black_frac >= 0.01 else 0
    img = ImageOps.autocontrast(img, cutoff=cutoff).point(lambda v: 0 if v < 150 else 255)
    img = _remove_rules(img)
    buf = BytesIO()
    img.save(buf, "PNG")
    png_bytes = buf.getvalue()
    tmp = pymupdf.open()
    new = tmp.new_page(width=page.rect.width, height=page.rect.height)
    new.insert_image(new.rect, stream=png_bytes)
    new.parent_doc = tmp  # mantener vivo el documento temporal mientras se use la página
    return new, png_bytes, angle


def _split_span(chars: list[dict], size: float):
    """Parte un span en fragmentos cuando entre dos caracteres hay un hueco grande.

    Los PDF exportados desde Excel guardan "$        1,234.00" como un solo texto con
    muchos espacios; aquí se separan en "$" y "1,234.00" con sus posiciones reales.
    """
    parts: list[list[dict]] = [[]]
    for ch in chars:
        if ch["c"].isspace():
            parts[-1].append(ch)
            continue
        cur = parts[-1]
        last = next((c for c in reversed(cur) if not c["c"].isspace()), None)
        if last is not None and ch["bbox"][0] - last["bbox"][2] > 0.9 * size:
            parts.append([])
        parts[-1].append(ch)
    for part in parts:
        visible = [c for c in part if not c["c"].isspace()]
        if not visible:
            continue
        text = "".join(c["c"] for c in part).strip()
        yield (
            text,
            min(c["bbox"][0] for c in visible),
            min(c["bbox"][1] for c in visible),
            max(c["bbox"][2] for c in visible),
            max(c["bbox"][3] for c in visible),
        )


def _merge_regions(regions: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    merged: list[pymupdf.Rect] = []
    for r in regions:
        for m in merged:
            if m.intersects(r):
                m |= r
                break
        else:
            merged.append(pymupdf.Rect(r))
    return merged


# ----------------------------------------------------------------------------- filas / segmentos

@dataclass
class Segment:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font: str
    size: float
    bold: bool
    italic: bool
    color: str
    rotation: float = 0.0


@dataclass
class Row:
    segments: list[Segment]
    y0: float
    y1: float


def group_rows(spans: list[Span]) -> list[Row]:
    """Agrupa el texto en filas visuales y une los fragmentos contiguos en segmentos."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s.cy, s.x0))
    clusters: list[list[Span]] = []
    centers: list[float] = []
    for sp in ordered:
        tol = max(2.0, 0.45 * sp.size)
        if clusters and abs(sp.cy - centers[-1]) <= tol:
            clusters[-1].append(sp)
            centers[-1] = sum(s.cy for s in clusters[-1]) / len(clusters[-1])
        else:
            clusters.append([sp])
            centers.append(sp.cy)

    rows: list[Row] = []
    for cluster in clusters:
        cluster.sort(key=lambda s: s.x0)
        segs: list[Segment] = []
        for sp in cluster:
            if segs and sp.x0 - segs[-1].x1 < 0.7 * sp.size and not _lone_currency(segs[-1].text):
                last = segs[-1]
                last.text += " " + sp.text
                last.x1 = max(last.x1, sp.x1)
                last.y0 = min(last.y0, sp.y0)
                last.y1 = max(last.y1, sp.y1)
            else:
                segs.append(Segment(sp.text, sp.x0, sp.y0, sp.x1, sp.y1, sp.font, sp.size, sp.bold, sp.italic, sp.color, sp.rotation))
        rows.append(Row(segs, min(s.y0 for s in segs), max(s.y1 for s in segs)))
    return rows


def _fix_ocr_numero(text: str) -> str:
    """Corrige el símbolo Nº mal leído por el OCR (solo texto OCR, nunca nativo).

    Tesseract con spa+eng lee el indicador ordinal masculino º (U+00BA) como
    "?" o "*" en muchos casos ("FACTURA N? 001-002-0001234" en vez de
    "FACTURA Nº ..."), y a veces como "N°" (signo de grado) o "No" seguido
    del número de factura. Esas formas no son palabras legítimas en español
    como token aislado ("N?", "N*"), así que la corrección es segura:
    - "N?" / "N*" (token completo) -> "Nº"
    - "N°" (token completo) -> "Nº" (los documentos usan Nº, no N°)
    - "No" + número de factura ecuatoriano (NNN-NNN-...) -> "Nº"
    """
    text = re.sub(r"(?<!\w)N[?*](?!\w)", "Nº", text)
    text = re.sub(r"(?<!\w)N°(?!\w)", "Nº", text)
    text = re.sub(r"\bNo(?=\s+\d{3}-\d{3}-\d)", "Nº", text)
    return text


def _lone_currency(text: str) -> bool:
    return text.strip() in {"$", "US$", "€", "£", "S/", "S/."}
