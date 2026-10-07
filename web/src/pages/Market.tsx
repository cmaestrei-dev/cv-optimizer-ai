import { useQuery } from "@tanstack/react-query";

import { get, type S } from "../api/client";
import { EmptyState, ErrorNotice, Spinner } from "../components/ui";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export function Market() {
  const market = useQuery({ queryKey: ["market"], queryFn: () => get<S["MarketOut"]>("/market") });
  if (market.isPending) return <Spinner />;
  if (market.error) return <ErrorNotice error={market.error} />;
  const m = market.data;
  return (
    <>
      <div className="page-head">
        <h1>Mi mercado</h1>
        <p>Qué piden las vacantes que has analizado y cómo te va en cada portal.</p>
      </div>
      {m.analyzed === 0 ? (
        <EmptyState title="Todavía no hay datos">Analiza algunas vacantes en la Bandeja y aquí verás qué palabras se repiten.</EmptyState>
      ) : (
        <>
          {!m.enough_data && <div className="notice info"><p>Con pocas postulaciones enviadas los porcentajes todavía no dicen mucho. Sigue registrando.</p></div>}
          <div className="metrics">
            <div className="metric"><b>{m.analyzed}</b><span>Vacantes analizadas</span></div>
            <div className="metric"><b>{m.sent}</b><span>Enviadas</span></div>
          </div>
          <section className="card">
            <h2>Lo que más piden</h2>
            <table>
              <thead><tr><th>Palabra clave</th><th>Vacantes</th><th>¿En tu perfil?</th></tr></thead>
              <tbody>
                {m.keywords.map((k) => (
                  <tr key={k.keyword}>
                    <td>{k.keyword}</td>
                    <td>
                      <div className="score"><div className="score-track"><div className="score-fill" style={{ width: `${Math.round(k.share * 100)}%` }} /></div><b>{k.vacancies}</b></div>
                    </td>
                    <td>{k.owned ? <span className="lvl cubre">Sí</span> : <span className="lvl no">No</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="card">
            <h2>Por portal</h2>
            <table>
              <thead><tr><th>Portal</th><th className="num">Guardadas</th><th className="num">Enviadas</th><th className="num">Avanzaron</th><th className="num">Compat. prom.</th></tr></thead>
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
          </section>
        </>
      )}
    </>
  );
}
