import { useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { AlertIcon, CheckIcon, CrossIcon, ExternalIcon, HalfIcon, RepeatIcon } from "./icons";

export function Spinner({ label = "Cargando" }: { label?: string }) {
  return (
    <span className="row" role="status">
      <span className="spinner" aria-hidden="true" />
      <span className="muted">{label}…</span>
    </span>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "ok" | "warn" | "bad"; children: ReactNode }) {
  return <div className={`notice ${kind}`} role={kind === "bad" ? "alert" : undefined}>{children}</div>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError || error instanceof Error ? error.message : "Algo salió mal.";
  return <Notice kind="bad"><p>{message}</p></Notice>;
}

/** Zona de la tabla según la compatibilidad: clasificación (≥75), repechaje (50–74), descenso (<50 o cerrada). */
export type Zone = "up" | "mid" | "down" | "none";

export function zoneOf(score: number | null | undefined, closed = false): Zone {
  if (closed) return "down";
  if (score === null || score === undefined) return "none";
  return score >= 75 ? "up" : score >= 50 ? "mid" : "down";
}

export const ZONE_LABEL: Record<Zone, string> = {
  up: "Zona de postulación",
  mid: "Repechaje",
  down: "Descenso",
  none: "Sin calcular",
};

/** Compatibilidad como numeral de marcador, con su zona. */
export function Score({ score, size = "md", label = "Compatibilidad" }: { score: number | null | undefined; size?: "md" | "lg"; label?: string }) {
  if (score === null || score === undefined) return <span className="score-num none" title="Sin calcular">—<span className="sr-only">{label} sin calcular</span></span>;
  return (
    <span className={`score-num ${size} ${zoneOf(score)}`} aria-label={`${label}: ${score} de 100`}>
      {score}
    </span>
  );
}

/** Barra proporcional (palabras clave, cupos): solo como apoyo de un número que se lee al lado. */
export function Bar({ value, max = 100 }: { value: number; max?: number }) {
  return <span className="bar" aria-hidden="true"><span style={{ width: `${Math.max(2, Math.min(100, (value / max) * 100))}%` }} /></span>;
}

export function CopyButton({ text, label = "Copiar" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="small"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? "Copiado" : label}
    </button>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <div className="muted">{children}</div>
    </div>
  );
}

const MARKS = {
  ok: [CheckIcon, "Cumples"],
  half: [HalfIcon, "A medias"],
  no: [CrossIcon, "Te falta"],
  warn: [AlertIcon, "Atención"],
  repeat: [RepeatIcon, "Repetida"],
} as const;

/** Estado con ícono dibujado y texto para lectores de pantalla (nunca solo color). */
export function Mark({ kind, label }: { kind: keyof typeof MARKS; label?: string }) {
  const [Icon, text] = MARKS[kind];
  return (
    <span className={`mark ${kind}`} title={label ?? text}>
      <Icon />
      <span className="sr-only">{label ?? text}</span>
    </span>
  );
}

const LEVEL = { cubre: "ok", parcial: "half", no: "no" } as const;

export function Level({ level }: { level: string }) {
  const kind = LEVEL[level as keyof typeof LEVEL];
  return kind ? <Mark kind={kind} /> : null;
}

/** Enlace a un sitio de terceros (ya pasado por safeHref). */
export function ExternalLink({ href, children, className = "btn small" }: { href: string | undefined; children: ReactNode; className?: string }) {
  if (!href) return null;
  return (
    <a className={className} href={href} target="_blank" rel="noopener noreferrer">
      {children}<ExternalIcon />
      <span className="sr-only"> (abre en otra pestaña)</span>
    </a>
  );
}
