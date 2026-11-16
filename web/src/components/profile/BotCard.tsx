// Conectar el bot de LinkedIn que corre en el computador de la persona: un token que se crea aquí,
// se copia una sola vez en la configuración del bot y se puede revocar cuando sea.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { del, get, post, type S } from "../../api/client";
import { ago, date } from "../../lib/format";
import { CopyButton, ErrorNotice, Notice } from "../ui";

export function BotCard() {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["bot-tokens"], queryFn: () => get<S["BotTokenOut"][]>("/bot-tokens") });
  const [label, setLabel] = useState("");
  const [created, setCreated] = useState<S["BotTokenCreatedOut"] | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const create = useMutation({
    mutationFn: () => post<S["BotTokenCreatedOut"]>("/bot-tokens", { label }),
    onSuccess: (out) => { setCreated(out); setLabel(""); queryClient.invalidateQueries({ queryKey: ["bot-tokens"] }); },
  });
  const revoke = useMutation({
    mutationFn: (id: number) => del(`/bot-tokens/${id}`),
    onSuccess: () => { setConfirming(null); queryClient.invalidateQueries({ queryKey: ["bot-tokens"] }); },
  });

  return (
    <section className="panel stack">
      <div>
        <h2 className="panel-title" style={{ marginBottom: 6 }}>Bot de LinkedIn</h2>
        <small>
          El bot corre en tu computador con tu sesión de LinkedIn y usa esta cuenta para analizar vacantes, hacer tu CV y
          registrar cada envío. Se conecta con un token: no necesita tu contraseña.
        </small>
      </div>

      {created && (
        <Notice kind="ok">
          <p><b>Copia este token ahora:</b> no se vuelve a mostrar. Pégalo en la configuración del bot.</p>
          <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start", marginTop: 8 }}>
            <code className="copy-box" style={{ flex: 1, minWidth: 0 }}>{created.token}</code>
            <CopyButton text={created.token} />
          </div>
          <button className="link" onClick={() => setCreated(null)}>Ya lo copié</button>
        </Notice>
      )}

      {list.data && list.data.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          {list.data.map((t) => (
            <div key={t.id} className="row spread" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
              <span>
                <b style={{ fontWeight: 600 }}>{t.label}</b> <small>· termina en {t.hint}</small>
                <small style={{ display: "block" }}>
                  Creado {date(t.created_at)} · {t.last_used_at ? `usado ${ago(t.last_used_at)}` : "sin usar todavía"}
                </small>
              </span>
              {confirming === t.id ? (
                <span className="row" style={{ flexWrap: "nowrap" }}>
                  <button className="small danger" onClick={() => revoke.mutate(t.id)} disabled={revoke.isPending}>Revocar</button>
                  <button className="small" onClick={() => setConfirming(null)}>No</button>
                </span>
              ) : (
                <button className="small ghost" onClick={() => setConfirming(t.id)}>Revocar</button>
              )}
            </div>
          ))}
        </div>
      )}

      <label>
        Nombre del equipo (opcional)
        <input type="text" value={label} maxLength={60} onChange={(e) => setLabel(e.target.value)} placeholder="Ej.: Mi portátil" />
      </label>
      <div><button className="primary small" onClick={() => create.mutate()} disabled={create.isPending}>Crear token del bot</button></div>
      <ErrorNotice error={create.error ?? revoke.error ?? list.error} />
    </section>
  );
}
