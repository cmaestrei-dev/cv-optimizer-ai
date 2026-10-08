// Alertas por correo: los portales mandan alertas de empleo; si la persona las reenvía (filtro de Gmail) a
// su dirección de la app, cada vacante llega sola a la bandeja, analizada. Aquí se activa y se guía el paso a paso.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { get, post, type S } from "../../api/client";
import { ago } from "../../lib/format";
import { CopyButton, ErrorNotice, Notice, Spinner } from "../ui";

const GMAIL_FORWARDING = "https://mail.google.com/mail/u/0/#settings/fwdandpop";

function Copyable({ text }: { text: string }) {
  return (
    <div className="row">
      <code className="copy-box" style={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{text}</code>
      <CopyButton text={text} />
    </div>
  );
}

function Steps({ alerts }: { alerts: S["AlertsOut"] }) {
  return (
    <ol className="stack" style={{ paddingLeft: 20, margin: 0 }}>
      <li>
        <b>Tu dirección de alertas</b> (solo para ti):
        <Copyable text={alerts.address} />
      </li>
      <li>
        En <b>Gmail desde un computador</b>: Configuración → <a href={GMAIL_FORWARDING} target="_blank" rel="noopener noreferrer">Reenvío y correo POP/IMAP ↗</a> →
        «Agregar una dirección de reenvío» → pega tu dirección.
        {alerts.forwarding_code ? (
          <Notice kind="ok">
            <p>Gmail pide este código de confirmación{alerts.forwarding_from && ` (para ${alerts.forwarding_from})`}: escríbelo donde te lo pide y pulsa «Verificar».</p>
            <Copyable text={alerts.forwarding_code} />
          </Notice>
        ) : (
          <small className="muted"> Gmail enviará un código de confirmación: aparecerá aquí en uno o dos minutos (pulsa «Revisar ahora»).</small>
        )}
      </li>
      <li>
        Crea un <b>filtro</b> para reenviar solo las alertas de empleo (el resto de tu correo no sale de Gmail): en el buscador de
        Gmail pega esto, abre las opciones de búsqueda (☰ a la derecha) → «Crear filtro» → marca «Reenviarlo a» con tu dirección → «Crear filtro».
        <Copyable text={alerts.gmail_filter} />
      </li>
      <li>
        En cada portal crea <b>alertas de empleo</b> con los cargos que buscas (en «Buscar vacantes en los portales», abre la búsqueda
        y usa el botón «Crear alerta» o «Activar alerta» del portal).
      </li>
    </ol>
  );
}

export function AlertsCard() {
  const queryClient = useQueryClient();
  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: () => get<S["AlertsOut"]>("/alerts"),
    refetchInterval: (q) => ((q.state.data?.analyzing ?? 0) > 0 ? 5000 : false),
  });
  const activate = useMutation({
    mutationFn: () => post<S["AlertsOut"]>("/alerts"),
    onSuccess: (data) => queryClient.setQueryData(["alerts"], data),
  });
  const check = useMutation({
    mutationFn: () => post<S["AlertsOut"]>("/alerts/check"),
    onSuccess: (data) => queryClient.setQueryData(["alerts"], data),
  });
  const rotate = useMutation({
    mutationFn: () => post<S["AlertsOut"]>("/alerts/rotate"),
    onSuccess: (data) => queryClient.setQueryData(["alerts"], data),
  });

  const active = Boolean(alerts.data?.address);
  const checked = useRef(false);
  const checkNow = check.mutate;
  useEffect(() => {  // al abrir la bandeja se revisa el buzón una vez (el servidor lo limita a una vez por minuto)
    if (active && !checked.current) {
      checked.current = true;
      checkNow();
    }
  }, [active, checkNow]);

  const analyzing = alerts.data?.analyzing ?? 0;
  const previous = useRef(analyzing);
  useEffect(() => {  // terminó un lote: las vacantes nuevas ya están en la bandeja
    if (analyzing < previous.current) queryClient.invalidateQueries({ queryKey: ["applications"] });
    previous.current = analyzing;
  }, [analyzing, queryClient]);

  if (!alerts.data?.enabled) return null;
  const data = alerts.data;
  const working = data.received_count > 0;

  if (!active) {
    return (
      <section className="card stack">
        <h2>Recibe vacantes sin buscarlas</h2>
        <p className="muted">
          LinkedIn, Computrabajo, elempleo y Magneto te mandan alertas de empleo por correo. Si las reenvías a la app, cada vacante
          llega sola a tu bandeja, analizada y ordenada según tu perfil. Sin contraseñas: solo un filtro en tu Gmail.
        </p>
        <ErrorNotice error={activate.error} />
        <div><button className="primary" onClick={() => activate.mutate()} disabled={activate.isPending}>Activar alertas por correo</button></div>
      </section>
    );
  }

  return (
    <section className="card stack">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Alertas por correo</h2>
        <button className="small" onClick={() => check.mutate()} disabled={check.isPending}>{check.isPending ? "Revisando…" : "Revisar ahora"}</button>
      </div>
      {working ? (
        <p>
          <span className="lvl cubre">✓</span> Funcionando · {data.received_count} {data.received_count === 1 ? "alerta recibida" : "alertas recibidas"}
          {data.last_received_at && `, la última ${ago(data.last_received_at)}`}.
          {data.last_summary && <><br /><small className="muted">{data.last_summary}</small></>}
        </p>
      ) : (
        <p className="muted">Aún no llega ninguna alerta. Sigue estos pasos (una sola vez):</p>
      )}
      {data.ignored_recently > 0 && (
        <Notice kind="warn">
          <p>
            Llegaron {data.ignored_recently} {data.ignored_recently === 1 ? "correo que no es" : "correos que no son"} alertas de empleo
            (se borraron sin guardarlos). Quizá Gmail está reenviando <b>todo</b> tu correo: en{" "}
            <a href={GMAIL_FORWARDING} target="_blank" rel="noopener noreferrer">Reenvío y correo POP/IMAP ↗</a> marca
            «Inhabilitar el reenvío» y guarda los cambios. Las alertas siguen llegando por el filtro.
          </p>
        </Notice>
      )}
      {analyzing > 0 && <Spinner label="Analizando vacantes de tus alertas" />}
      {data.waiting > 0 && (
        <small className="muted">
          {data.waiting} {data.waiting === 1 ? "vacante espera" : "vacantes esperan"} turno: se analizan al día siguiente (tope diario) o
          cuando registres tu experiencia en Perfil.
        </small>
      )}
      <ErrorNotice error={check.error ?? rotate.error} />
      {working ? (
        <details>
          <summary>Ver los pasos de configuración</summary>
          <div style={{ marginTop: 12 }}><Steps alerts={data} /></div>
        </details>
      ) : (
        <Steps alerts={data} />
      )}
      <details>
        <summary><small>Cambiar mi dirección</small></summary>
        <div className="stack" style={{ marginTop: 8 }}>
          <small className="muted">Úsalo si compartiste tu dirección por error: la actual deja de funcionar y tendrás que poner la nueva en Gmail (reenvío y filtro).</small>
          <div><button className="small danger" disabled={rotate.isPending}
            onClick={() => window.confirm("Tu dirección actual dejará de recibir alertas hasta que pongas la nueva en Gmail. ¿Continuar?") && rotate.mutate()}>
            Crear una dirección nueva
          </button></div>
        </div>
      </details>
      <small className="faint">Se analizan hasta {data.daily_limit} vacantes de alertas al día. Los correos se borran apenas se leen.</small>
    </section>
  );
}
