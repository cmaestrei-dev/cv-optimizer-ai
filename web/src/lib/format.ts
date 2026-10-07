export function date(value: string | null | undefined): string {
  if (!value) return "";
  // Solo fecha: mediodía local (evita saltar de día). Fecha y hora sin zona (SQLite): es UTC.
  const iso = value.length === 10 ? `${value}T12:00:00` : /([zZ]|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
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
