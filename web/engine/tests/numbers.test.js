import { describe, expect, it } from "vitest";
import { parseNumber } from "../src/numbers.js";

describe("parseNumber (puerto de app/converters/numbers.py)", () => {
  it("cifras con formato contable EE. UU.", () => {
    expect(parseNumber("$ 30,570.51")).toMatchObject({ value: 30570.51, currency: "$" });
    expect(parseNumber("1,234.00")).toMatchObject({ value: 1234 });
    expect(parseNumber("27,948.96")).toMatchObject({ value: 27948.96 });
  });

  it("formato europeo (coma decimal)", () => {
    expect(parseNumber("2.621,55")).toMatchObject({ value: 2621.55 });
    expect(parseNumber("1.234,56")).toMatchObject({ value: 1234.56 });
  });

  it("negativos entre paréntesis y con guion", () => {
    expect(parseNumber("(1,234.00)")).toMatchObject({ value: -1234 });
    expect(parseNumber("(1,234.00)").numberFormat).toContain(";");
    expect(parseNumber("-50.00")).toMatchObject({ value: -50 });
    expect(parseNumber("1,234.00-")).toMatchObject({ value: -1234 });
  });

  it("porcentajes", () => {
    expect(parseNumber("15%")).toMatchObject({ value: 0.15 });
    expect(parseNumber("12.5%")).toMatchObject({ value: 0.125 });
  });

  it("códigos que deben seguir siendo texto", () => {
    expect(parseNumber("0993132977001")).toBeNull(); // RUC
    expect(parseNumber("0418-2018")).toBeNull();
    expect(parseNumber("01-Octubre-26")).toBeNull();
    expect(parseNumber("001-002-0001234")).toBeNull();
  });

  it("miles con espacios y moneda suelta", () => {
    expect(parseNumber("1 234.00")).toMatchObject({ value: 1234 });
    expect(parseNumber("US$ 100.00")).toMatchObject({ value: 100, currency: "US$" });
    expect(parseNumber("$")).toBeNull();
  });

  it("formatos contables generados", () => {
    expect(parseNumber("$ 1,234.00").numberFormat).toBe('"$"#,##0.00');
    expect(parseNumber("1234").numberFormat).toBe("#,##0");
    expect(parseNumber("5").numberFormat).toBe("0");
    expect(parseNumber("0.50").numberFormat).toBe("#,##0.00");
  });
});
