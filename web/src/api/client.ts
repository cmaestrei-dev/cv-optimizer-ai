// Cliente de la API: token, errores legibles, descargas y seguimiento de trabajos en segundo plano.
import type { components } from "./schema";

export type S = components["schemas"];
export type Job = S["JobOut"];

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

type TokenGetter = () => Promise<string | null> | string | null;
let getToken: TokenGetter = () => null;
let onUnauthorized: () => void = () => {};

export function configureAuth(tokenGetter: TokenGetter, unauthorized: () => void): void {
  getToken = tokenGetter;
  onUnauthorized = unauthorized;
}

export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const fields = detail
      .map((d) => (d as { msg?: string }).msg?.replace(/^Value error, /, ""))
      .filter(Boolean);
    return fields.length ? `Revisa los datos: ${fields.join("; ")}` : "Revisa los datos e intenta de nuevo.";
  }
  if (status === 413) return "El archivo es demasiado grande.";
  if (status >= 500) return "Algo falló de nuestro lado. Intenta de nuevo en un momento.";
  return "No se pudo completar. Intenta de nuevo.";
}

async function request(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = await getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "No hay conexión con el servidor. Revisa tu internet e intenta de nuevo.");
  }
  if (res.status === 401) onUnauthorized();
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      // cuerpo vacío o no JSON
    }
    throw new ApiError(res.status, errorMessage(parsed, res.status), parsed);
  }
  return res;
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await request(method, path, body);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const get = <T,>(path: string) => api<T>("GET", path);
export const post = <T,>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const put = <T,>(path: string, body: unknown) => api<T>("PUT", path, body);
export const patch = <T,>(path: string, body: unknown) => api<T>("PATCH", path, body);
export const del = <T,>(path: string) => api<T>("DELETE", path);

/** Descarga un archivo protegido (el navegador no puede mandar el token en un enlace normal). */
export async function download(path: string, fallbackName: string): Promise<void> {
  const res = await request("GET", path);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename\*=UTF-8''([^;]+)/.exec(disposition);
  const name = match?.[1] ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Espera a que un trabajo termine, informando el avance. Lanza ApiError si falla. */
export async function waitForJob(
  id: number,
  onProgress?: (job: Job) => void,
  { intervalMs = 1500, timeoutMs = 10 * 60_000 } = {},
): Promise<Job> {
  const started = Date.now();
  for (;;) {
    const job = await get<Job>(`/jobs/${id}`);
    onProgress?.(job);
    if (job.status === "done") return job;
    if (job.status === "failed") throw new ApiError(500, job.error || "El trabajo no se pudo completar.", job);
    if (Date.now() - started > timeoutMs) throw new ApiError(504, "Esto está tardando demasiado. Revisa más tarde.");
    await sleep(intervalMs);
  }
}

/** Solo enlaces http(s) en href (los datos pueden venir de páginas de terceros). */
export function safeHref(url: string | null | undefined): string | undefined {
  return url && /^https?:\/\//i.test(url) ? url : undefined;
}
