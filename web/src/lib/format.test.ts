import { describe, expect, it } from "vitest";

import { ago, date, freshness, number } from "./format";

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

describe("ago", () => {
  const now = new Date("2026-10-08T15:00:00Z").getTime();
  it("minutos y horas; sin zona es UTC", () => {
    expect(ago("2026-10-08T14:55:00Z", now)).toBe("hace 5 min");
    expect(ago("2026-10-08T12:00:00", now)).toBe("hace 3 h");
    expect(ago("2026-10-08T14:59:50+00:00", now)).toBe("hace un momento");
  });
  it("más de un día: la fecha", () => {
    expect(ago("2026-10-05T15:00:00Z", now)).toBe(date("2026-10-05T15:00:00Z"));
  });
});

describe("freshness", () => {
  it("edad y cierre", () => {
    expect(freshness("2026-10-05", "2026-11-20", "2026-10-08")).toEqual({
      text: `Publicada hace 3 días · cierra ${date("2026-11-20")}`, stale: false, closed: false,
    });
  });
  it("vieja, por cerrar o cerrada", () => {
    expect(freshness("2026-08-01", null, "2026-10-08")?.stale).toBe(true);
    expect(freshness(null, "2026-10-10", "2026-10-08")).toEqual({ text: "cierra en 2 días", stale: true, closed: false });
    expect(freshness("2026-09-01", "2026-10-07", "2026-10-08")?.closed).toBe(true);
    expect(freshness(null, null, "2026-10-08")).toBeNull();
  });
});
