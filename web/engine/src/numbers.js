/**
 * Interpretación de números tal como aparecen en un PDF (formato contable,
 * EE. UU. o español). Traducción fiel de app/converters/numbers.py.
 *
 * Reglas pensadas para no dañar códigos: "0993132977001" (RUC), "0418-2018" o
 * "01-Octubre-26" se dejan como texto.
 */

const CURRENCY = /^(US\$|S\/\.?|[$€£])\s*/;

/**
 * @param {string} text
 * @returns {{ value: number, numberFormat: string, currency: string } | null}
 */
export function parseNumber(text) {
  let t = String(text ?? "").trim();
  if (!t) return null;

  let negative = false;
  if (t.startsWith("(") && t.endsWith(")")) {
    negative = true;
    t = t.slice(1, -1).trim();
  }

  let currency = "";
  const m = CURRENCY.exec(t);
  if (m) {
    currency = m[1];
    t = t.slice(m[0].length);
  }

  if (t.startsWith("-")) {
    negative = true;
    t = t.slice(1).trim();
  } else if (t.endsWith("-") && t.length > 1) {
    // contabilidad: 1,234.00-
    negative = true;
    t = t.slice(0, -1).trim();
  }

  const percent = t.endsWith("%");
  if (percent) t = t.slice(0, -1).trim();

  if (!/^\d[\d.,\s]*$/.test(t)) return null;
  t = t.replace(/(?<=\d)\s(?=\d{3}\b)/g, ""); // "1 234" -> "1234"
  if (t.includes(" ")) return null;

  const hasDot = t.includes(".");
  const hasComma = t.includes(",");
  let decSep = "";
  let thouSep = "";
  if (hasDot && hasComma) {
    decSep = t.lastIndexOf(".") > t.lastIndexOf(",") ? "." : ",";
    thouSep = decSep === "." ? "," : ".";
  } else if (hasDot || hasComma) {
    const sep = hasDot ? "." : ",";
    const parts = t.split(sep);
    if (parts.length > 2) {
      // varios separadores iguales -> miles
      decSep = "";
      thouSep = sep;
    } else if (parts[1].length === 3 && parts[0].length >= 1 && parts[0].length <= 3) {
      // 1,234 -> miles
      decSep = "";
      thouSep = sep;
    } else {
      decSep = sep;
      thouSep = "";
    }
  }

  let integerPart = t;
  let frac = "";
  if (decSep) {
    const idx = t.lastIndexOf(decSep);
    integerPart = t.slice(0, idx);
    frac = t.slice(idx + 1);
  }
  if (thouSep) {
    const groups = integerPart.split(thouSep);
    if (!(groups[0].length >= 1 && groups[0].length <= 3 && groups.slice(1).every((g) => g.length === 3))) {
      return null;
    }
    integerPart = groups.join("");
  }
  if (!/^\d+$/.test(integerPart) || (frac && !/^\d+$/.test(frac))) return null;

  // Códigos: ceros a la izquierda o cadenas larguísimas sin separadores
  if (!thouSep && !decSep && ((integerPart.startsWith("0") && integerPart.length > 1) || integerPart.length > 15)) {
    return null;
  }
  if (integerPart.startsWith("0") && integerPart.length > 1 && !decSep) return null;

  const decimals = frac.length;
  let value = parseFloat(frac ? `${integerPart}.${frac}` : integerPart);
  if (negative) value = -value;
  if (percent) {
    value /= 100;
    return {
      value,
      numberFormat: `0${decimals ? `.${"0".repeat(decimals)}` : ""}%`,
      currency,
    };
  }

  let base = "#,##0";
  if (!thouSep && value < 1000 && !decimals) base = "0";
  if (decimals) base += `.${"0".repeat(decimals)}`;
  if (currency) base = `"${currency}"${base}`;
  const fmt =
    negative && String(text).trim().startsWith("(") ? `${base};(${base})` : base;
  return { value, numberFormat: fmt, currency };
}

/** ¿Es el texto un símbolo de moneda suelto ("$", "US$", "€", "£", "S/")? */
export function isLoneCurrency(text) {
  return ["$", "US$", "€", "£", "S/", "S/."].includes(String(text ?? "").trim());
}
