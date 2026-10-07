import { useState, type ReactNode } from "react";

import { ApiError } from "../api/client";

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

export function ScoreBar({ score, label = "Compatibilidad" }: { score: number | null | undefined; label?: string }) {
  if (score === null || score === undefined) return <small className="muted">Sin calcular</small>;
  return (
    <div className="score" aria-label={`${label}: ${score} de 100`}>
      <div className="score-track"><div className="score-fill" style={{ width: `${Math.max(2, score)}%` }} /></div>
      <b>{score}</b>
    </div>
  );
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
    <div className="card">
      <h3>{title}</h3>
      <div className="muted">{children}</div>
    </div>
  );
}

const LEVEL = { cubre: ["✓", "Cumples"], parcial: ["½", "A medias"], no: ["✗", "Te falta"] } as const;

export function Level({ level }: { level: string }) {
  const [mark, text] = LEVEL[level as keyof typeof LEVEL] ?? ["·", level];
  return (
    <span className={`lvl ${level}`} title={text}>
      {mark}
      <span className="sr-only">{text}</span>
    </span>
  );
}
