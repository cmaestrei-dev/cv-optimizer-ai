export function date(value: string | null | undefined): string {
  if (!value) return "";
  // Solo fecha: mediodía local (evita saltar de día). Fecha y hora sin zona (SQLite): es UTC.
  const iso = value.length === 10 ? `${value}T12:00:00` : /([zZ]|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
}

/** "hace 5 min", "hace 3 h"; más de un día: la fecha. */
export function ago(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return "";
  const iso = /([zZ]|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "hace un momento";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `hace ${hours} h` : date(value);
}

/** Qué tan vigente está una vacante: "Publicada hace 3 días · cierra 25 oct". `stale` = vieja o por cerrar. */
export function freshness(
  posted: string | null | undefined,
  closes: string | null | undefined,
  now: string = today(),
): { text: string; stale: boolean; closed: boolean } | null {
  const days = (a: string, b: string) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 86_400_000);
  const parts: string[] = [];
  let stale = false;
  let closed = false;
  if (posted) {
    const age = days(posted, now);
    parts.push(age <= 0 ? "Publicada hoy" : age === 1 ? "Publicada ayer" : `Publicada hace ${age} días`);
    stale = age > 30;
  }
  if (closes) {
    const left = days(now, closes);
    closed = left < 0;
    parts.push(closed ? "ya cerró" : left === 0 ? "cierra hoy" : left <= 3 ? `cierra en ${left} ${left === 1 ? "día" : "días"}` : `cierra ${date(closes)}`);
    stale = stale || left <= 3;
  }
  return parts.length ? { text: parts.join(" · "), stale, closed } : null;
}

export function number(value: number): string {
  return value.toLocaleString("es-CO", { maximumFractionDigits: 1 });
}

export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const PLATFORMS = ["LinkedIn", "Computrabajo", "Magneto", "elempleo", "Página de la empresa", "Correo o referido", "Otra"];

export const STATUS_LABELS: Record<string, string> = {
  por_revisar: "Por revisar",
  guardada: "Guardada",
  cv_generado: "CV listo",
  postulada: "Postulada",
  en_revision: "En revisión",
  entrevista: "Entrevista",
  oferta: "Oferta",
  rechazada: "Rechazada",
  retirada: "Retirada",
  descartada: "Descartada",
};
