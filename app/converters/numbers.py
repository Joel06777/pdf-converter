"""Interpretación de números tal como aparecen en un PDF (formato contable, EE. UU. o español)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_CURRENCY = re.compile(r"^(US\$|S/\.?|[$€£])\s*")


@dataclass
class ParsedNumber:
    value: float
    number_format: str
    currency: str = ""


def parse_number(text: str) -> ParsedNumber | None:
    """Devuelve el valor numérico real de un texto, o None si no es un número.

    Reglas pensadas para no dañar códigos: "0993132977001" (RUC), "0418-2018" o
    "01-Octubre-26" se dejan como texto.
    """
    t = text.strip()
    if not t:
        return None

    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1].strip()

    currency = ""
    m = _CURRENCY.match(t)
    if m:
        currency, t = m.group(1), t[m.end():]

    if t.startswith("-"):
        negative, t = True, t[1:].strip()
    elif t.endswith("-") and len(t) > 1:  # contabilidad: 1,234.00-
        negative, t = True, t[:-1].strip()

    percent = t.endswith("%")
    if percent:
        t = t[:-1].strip()

    if not re.fullmatch(r"\d[\d.,\s]*", t):
        return None
    t = re.sub(r"(?<=\d)\s(?=\d{3}\b)", "", t)  # "1 234" -> "1234"
    if " " in t:
        return None

    has_dot, has_comma = "." in t, "," in t
    decimals = 0
    if has_dot and has_comma:
        dec_sep = "." if t.rfind(".") > t.rfind(",") else ","
        thou_sep = "," if dec_sep == "." else "."
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        parts = t.split(sep)
        if len(parts) > 2:  # varios separadores iguales -> miles
            dec_sep, thou_sep = "", sep
        elif len(parts[1]) == 3 and 1 <= len(parts[0]) <= 3:  # 1,234 -> miles
            dec_sep, thou_sep = "", sep
        else:
            dec_sep, thou_sep = sep, ""
    else:
        dec_sep, thou_sep = "", ""

    integer_part = t
    frac = ""
    if dec_sep:
        integer_part, _, frac = t.rpartition(dec_sep)
    if thou_sep:
        groups = integer_part.split(thou_sep)
        if not (1 <= len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:])):
            return None
        integer_part = "".join(groups)
    if not integer_part.isdigit() or (frac and not frac.isdigit()):
        return None

    # Códigos: ceros a la izquierda o cadenas larguísimas sin separadores
    if not thou_sep and not dec_sep and ((integer_part.startswith("0") and len(integer_part) > 1) or len(integer_part) > 15):
        return None
    if integer_part.startswith("0") and len(integer_part) > 1 and not dec_sep:
        return None

    decimals = len(frac)
    value = float(f"{integer_part}.{frac}" if frac else integer_part)
    if negative:
        value = -value
    if percent:
        value /= 100
        return ParsedNumber(value, "0" + ("." + "0" * decimals if decimals else "") + "%", currency)

    base = "#,##0" if (thou_sep or value >= 1000 or decimals) else "0"
    if thou_sep or value >= 1000:
        base = "#,##0"
    if decimals:
        base += "." + "0" * decimals
    if currency:
        base = f'"{currency}"{base}'
    fmt = f"{base};({base})" if (negative and text.strip().startswith("(")) else base
    return ParsedNumber(value, fmt, currency)
