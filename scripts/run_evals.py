"""Evalúa el motor de CV con perfiles y vacantes ficticios (evals/cases.py) y compara proveedores.

Uso:
  python scripts/run_evals.py                          # gemini
  python scripts/run_evals.py --providers gemini deepseek
  python scripts/run_evals.py --providers gemini/deepseek   # extraer con gemini, redactar con deepseek
  python scripts/run_evals.py --cases ventas dev_backend

Hace llamadas reales a la IA (cuesta cuota). No usa base de datos. Guarda el detalle en evals/results/.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402,F401  (carga .env)
from core.engine.pipeline import analyze, generate  # noqa: E402
from core.llm import get_llm  # noqa: E402
from evals.cases import CASES, PROFILES  # noqa: E402
from evals.metrics import (  # noqa: E402
    CaseResult,
    CountingLLM,
    keyword_coverage,
    language_ok,
    match_accuracy,
)


def run_case(case, extract: str, write: str) -> CaseResult:
    os.environ["LLM_EXTRACT"], os.environ["LLM_WRITE"] = extract, write
    result = CaseResult(case=case.name, provider=extract if extract == write else f"{extract}/{write}")
    profile, contact = PROFILES[case.profile]
    llm_extract, llm_write = CountingLLM(get_llm("extract")), CountingLLM(get_llm("write"))
    started = time.perf_counter()
    try:
        analysis = analyze(llm_extract, profile, text=case.vacancy)
        result.score = analysis.match.score
        result.match_hits, result.match_total, result.match_misses = match_accuracy(case, analysis)
        generated = generate(llm_write, profile, contact, analysis)
        result.bullets = sum(len(e.bullets) for e in generated.document.experiences)
        result.reverted = len(generated.reverted)
        result.summary_replaced = generated.summary_replaced
        result.pages = generated.output.pages
        result.language_ok = language_ok(generated, case.language)
        result.keyword_coverage = keyword_coverage(analysis, profile, generated.document.to_markdown())
    except Exception as e:  # una falla no detiene la evaluación
        result.error = f"{type(e).__name__}: {str(e)[:200]}"
    result.seconds = time.perf_counter() - started
    result.llm_calls = llm_extract.calls + llm_write.calls
    return result


def summarize(results: list[CaseResult]) -> str:
    rows = ["| Proveedor | Match | Inventado (viñetas revertidas) | Resumen reemplazado | 1 página | Idioma | Keywords en CV | Llamadas | Tiempo/caso | Errores |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for provider in dict.fromkeys(r.provider for r in results):
        rs = [r for r in results if r.provider == provider]
        ok = [r for r in rs if not r.error]
        hits = sum(r.match_hits for r in ok)
        total = sum(r.match_total for r in ok) or 1
        bullets = sum(r.bullets for r in ok) or 1
        rows.append(
            f"| {provider} | {hits}/{total} ({hits / total:.0%}) | {sum(r.reverted for r in ok)}/{bullets} "
            f"| {sum(r.summary_replaced for r in ok)}/{len(ok)} | {sum(r.pages == 1 for r in ok)}/{len(ok)} "
            f"| {sum(r.language_ok for r in ok)}/{len(ok)} "
            f"| {sum(r.keyword_coverage for r in ok) / max(len(ok), 1):.0%} "
            f"| {sum(r.llm_calls for r in rs) / len(rs):.1f} | {sum(r.seconds for r in rs) / len(rs):.1f}s "
            f"| {sum(bool(r.error) for r in rs)} |"
        )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--providers", nargs="+", default=["gemini"], help="proveedor o extraer/redactar")
    parser.add_argument("--cases", nargs="+", help="nombres de casos (por defecto, todos)")
    args = parser.parse_args()

    cases = [c for c in CASES if not args.cases or c.name in args.cases]
    results = []
    for spec in args.providers:
        extract, _, write = spec.partition("/")
        for case in cases:
            r = run_case(case, extract, write or extract)
            results.append(r)
            status = f"ERROR {r.error}" if r.error else (
                f"puntaje {r.score}, match {r.match_hits}/{r.match_total}, revertidas {r.reverted}/{r.bullets}, "
                f"{r.pages} pág, {r.seconds:.1f}s"
            )
            print(f"[{r.provider}] {case.name}: {status}")
            for miss in r.match_misses:
                print(f"    · {miss}")

    print("\n" + summarize(results))
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals", "results")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, time.strftime("%Y%m%d-%H%M%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
    print(f"\nDetalle: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
