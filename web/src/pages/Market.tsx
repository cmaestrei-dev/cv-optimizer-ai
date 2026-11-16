import { useQuery } from "@tanstack/react-query";

import { get, type S } from "../api/client";
import { Bar, EmptyState, ErrorNotice, Mark, Notice, Spinner } from "../components/ui";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export function Market() {
  const market = useQuery({ queryKey: ["market"], queryFn: () => get<S["MarketOut"]>("/market") });
  if (market.isPending) return <Spinner />;
  if (market.error) return <ErrorNotice error={market.error} />;
  const m = market.data;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Mercado</h1>
          <p>Qué piden las vacantes que has analizado y cómo te va en cada portal.</p>
        </div>
        {m.analyzed > 0 && (
          <div className="metrics-line">
            <div>{m.analyzed}<small>Vacantes analizadas</small></div>
            <div>{m.sent}<small>Enviadas</small></div>
          </div>
        )}
      </div>
      {m.analyzed === 0 ? (
        <EmptyState title="Todavía no hay datos">Analiza algunas vacantes en la Bandeja y aquí verás qué palabras se repiten.</EmptyState>
      ) : (
        <>
          {!m.enough_data && <Notice kind="info"><p>Con pocas postulaciones enviadas los porcentajes todavía no dicen mucho. Sigue registrando.</p></Notice>}
          <div className="with-rail" style={{ gridTemplateColumns: undefined }}>
            <section className="section">
              <div className="section-head"><h2>Lo que más piden</h2><small>{m.keywords.length} palabras</small></div>
              <div className="standings">
                <table>
                  <thead><tr><th scope="col">Palabra clave</th><th scope="col" style={{ width: "40%" }}>Vacantes que la piden</th><th scope="col">¿En tu perfil?</th></tr></thead>
                  <tbody>
                    {m.keywords.map((k) => (
                      <tr key={k.keyword}>
                        <td><b style={{ fontWeight: 600 }}>{k.keyword}</b></td>
                        <td><span className="row" style={{ flexWrap: "nowrap", gap: 10 }}><Bar value={Math.round(k.share * 100)} /><b className="num" style={{ font: "700 1.05rem/1 var(--display)" }}>{k.vacancies}</b></span></td>
                        <td>{k.owned ? <span className="row"><Mark kind="ok" /> Sí</span> : <span className="row"><Mark kind="no" /> No</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="section">
              <div className="section-head"><h2>Por portal</h2></div>
              <div className="standings" style={{ overflowX: "auto" }}>
                <table>
                  <thead><tr><th scope="col">Portal</th><th className="num" scope="col">Guard.</th><th className="num" scope="col">Env.</th><th className="num" scope="col">Avanz.</th><th className="num" scope="col">Compat.</th></tr></thead>
                  <tbody>
                    {m.platforms.map((p) => (
                      <tr key={p.platform}>
                        <td>{p.platform}</td><td className="num">{p.saved}</td><td className="num">{p.sent}</td>
                        <td className="num">{pct(p.progress_rate)}</td>
                        <td className="num">{p.avg_score === null || p.avg_score === undefined ? "—" : Math.round(p.avg_score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <small className="faint" style={{ display: "block", marginTop: 8 }}>Guard.: guardadas · Env.: enviadas · Avanz.: avanzaron · Compat.: compatibilidad promedio</small>
            </section>
          </div>
        </>
      )}
    </>
  );
}
