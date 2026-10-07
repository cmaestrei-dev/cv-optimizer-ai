import { describe, expect, it } from "vitest";

import { date, number } from "./format";

describe("date", () => {
  it("una fecha y hora sin zona (SQLite) es UTC: 23:30 UTC sigue siendo el mismo día en Bogotá", () => {
    const shown = date("2026-10-07T23:30:00");
    expect(shown).toBe(new Date("2026-10-07T23:30:00Z").toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" }));
  });
  it("una fecha sola no salta de día", () => {
    expect(date("2026-10-07")).toMatch(/7/);
  });
});

describe("number", () => {
  it("usa coma decimal", () => {
    expect(number(7.8)).toBe("7,8");
  });
});
