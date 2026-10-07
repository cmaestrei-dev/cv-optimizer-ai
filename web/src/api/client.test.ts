import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, configureAuth, errorMessage, safeHref, waitForJob } from "./client";

function respond(status: number, body: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("errorMessage", () => {
  it("usa el detalle de la API o un mensaje en español", () => {
    expect(errorMessage({ detail: "Ya tienes esta vacante" }, 409)).toBe("Ya tienes esta vacante");
    expect(errorMessage({ detail: [{ msg: "Value error, El enlace no es válido" }] }, 422)).toBe("Revisa los datos: El enlace no es válido");
    expect(errorMessage(null, 413)).toBe("El archivo es demasiado grande.");
    expect(errorMessage(null, 502)).toMatch(/de nuestro lado/);
  });
});

describe("safeHref", () => {
  it("solo deja pasar http(s)", () => {
    expect(safeHref("https://co.computrabajo.com/x")).toBe("https://co.computrabajo.com/x");
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("data:text/html,hola")).toBeUndefined();
    expect(safeHref("")).toBeUndefined();
  });
});

describe("api", () => {
  it("manda el token y lanza ApiError con el mensaje del servidor", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(422, { detail: "Registra primero tu experiencia" }));
    vi.stubGlobal("fetch", fetchMock);
    configureAuth(() => "tok", () => {});
    await expect(api("POST", "/vacancies", { text: "x" })).rejects.toMatchObject({ status: 422, message: "Registra primero tu experiencia" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/vacancies");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("cierra la sesión ante un 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(401, { detail: "Token inválido o vencido" })));
    const signOut = vi.fn();
    configureAuth(() => "viejo", signOut);
    await expect(api("GET", "/me")).rejects.toBeInstanceOf(ApiError);
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("sin conexión da un mensaje claro", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api("GET", "/me")).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/conexión/) });
  });
});

describe("waitForJob", () => {
  it("informa el avance hasta terminar", async () => {
    const states = [
      { id: 1, status: "running", result: { done: 1, total: 2 } },
      { id: 1, status: "done", result: { done: 2, total: 2 } },
    ];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(respond(200, states.shift()))));
    const seen: string[] = [];
    const job = await waitForJob(1, (j) => seen.push(j.status), { intervalMs: 1 });
    expect(job.status).toBe("done");
    expect(seen).toEqual(["running", "done"]);
  });

  it("un trabajo fallido lanza su mensaje", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(200, { id: 2, status: "failed", error: "La IA no está disponible" })));
    await expect(waitForJob(2, undefined, { intervalMs: 1 })).rejects.toMatchObject({ message: "La IA no está disponible" });
  });
});
