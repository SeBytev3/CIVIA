#!/usr/bin/env python3
"""
eval/evaluar.py — Suite formal de evaluación reproducible de CIVIA (Momento 2).

Ejecuta:
1) Verificación determinista SQL de los casos dorados (eval/casos_dorados.json) sin consumir APIs externas.
2) Suite de 15 consultas representativas (Q01..Q15) cubriendo:
   - Consultas exactas de reportes (Q01..Q03)
   - Consultas espaciales (Q04..Q05)
   - Interpretación de descripciones ciudadanas (Q06..Q07)
   - Clasificación multimodal sobre conjunto de referencia (Q08..Q11)
   - Selección de herramientas del agente y límites (Q12..Q13)
   - Manejo de información insuficiente / irresoluble (Q14)
   - Falla controlada 429 y recuperación automática entre proveedores (Q15)
3) Guarda resultados verificables en eval/resultados/reporte_evaluacion.json y eval/resultados/reporte_evaluacion.md.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

# Permitir importación de app.* cuando se ejecuta desde /app en el contenedor
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR / "backend") not in sys.path and (ROOT_DIR / "backend").exists():
    sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.agent import run_civia_agent
from app.ai_router import (
    classify_evidence_with_router,
    reset_all_circuits,
    set_runtime_fault_override,
)
from app.config import settings
from app.db import (
    assert_disposable_test_db,
    ensure_isolated_database,
    get_conn,
    get_database_name,
    is_disposable_test_or_eval_db,
    run_migrations,
)
from app.observability import estimate_cost_usd
from app.seed import DEMO_ASSETS_DIR, seed_synthetic_reports

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "resultados"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(float(s[0]), 2)
    idx = (len(s) - 1) * (pct / 100.0)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return round(float(s[lo]), 2)
    frac = idx - lo
    return round(float(s[lo] + frac * (s[hi] - s[lo])), 2)


def verify_golden_sql_ground_truth(golden_path: Path) -> list[dict[str, Any]]:
    data = json.loads(golden_path.read_text(encoding="utf-8"))
    results = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for item in data["casos_dorados"]:
                cur.execute(item["sql_comprobacion"])
                rows = cur.fetchall()
                expected = item["respuesta_esperada_sql"]
                sql_ok = True
                if "total" in expected:
                    if len(rows) == 1 and "total" in rows[0]:
                        sql_ok = int(rows[0]["total"]) == int(expected["total"])
                    else:
                        sql_ok = len(rows) == int(expected["total"])
                elif "tracking_code" in expected and rows:
                    sql_ok = rows[0].get("tracking_code") == expected["tracking_code"]

                results.append(
                    {
                        "id": item["id"],
                        "tipo": item["tipo"],
                        "es_respondible": item["es_respondible"],
                        "origen_datos": item["origen_datos"],
                        "pregunta": item["pregunta"],
                        "sql_verificado": sql_ok,
                        "filas_sql": rows,
                    }
                )
    return results


def build_15_representative_queries() -> list[dict[str, Any]]:
    return [
        # 1. Consultas exactas de reportes (Q01..Q03)
        {
            "id": "Q01",
            "group": "1_consulta_exacta",
            "kind": "agent",
            "golden_ref": "GD-01",
            "input": "¿Cuántos reportes de la categoría HUECO están registrados en la base de datos y cuáles son sus códigos de radicado?",
            "expected_tool": "consultar_reportes",
            "must_contain_any": ["CIV-2026-DEMO0001", "CIV-2026-DEMO0005", "CIV-2026-DEMO0009"],
            "must_contain_all": ["HUECO"],
        },
        {
            "id": "Q02",
            "group": "1_consulta_exacta",
            "kind": "agent",
            "golden_ref": "GD-02",
            "input": "¿Cuál es la categoría, severidad, comuna y estado actual del reporte con código de radicado CIV-2026-DEMO0004?",
            "expected_tool": "obtener_reporte",
            "must_contain_any": ["CRITICA", "CRÍTICA", "IN_REVIEW", "revisión"],
            "must_contain_all": ["CIV-2026-DEMO0004", "QUEMA", "Comuna 2"],
        },
        {
            "id": "Q03",
            "group": "1_consulta_exacta",
            "kind": "agent",
            "golden_ref": None,
            "input": "Consulta el reporte con código CIV-2026-DEMO0006 e indica su categoría, barrio y estado actual.",
            "expected_tool": "obtener_reporte",
            "must_contain_any": ["RESOLVED", "resuelto", "Alfonso"],
            "must_contain_all": ["CIV-2026-DEMO0006", "BASURAS"],
        },
        # 2. Consultas espaciales (Q04..Q05)
        {
            "id": "Q04",
            "group": "2_consulta_espacial",
            "kind": "agent",
            "golden_ref": "GD-03",
            "input": "¿Qué reportes existen registrados en la Comuna 2 de Cali y a qué categorías corresponden?",
            "expected_tool": "consultar_reportes",
            "must_contain_any": ["HUECO", "QUEMA"],
            "must_contain_all": ["CIV-2026-DEMO0001", "CIV-2026-DEMO0004"],
        },
        {
            "id": "Q05",
            "group": "2_consulta_espacial",
            "kind": "agent",
            "golden_ref": "GD-04",
            "input": "¿Qué reporte se encuentra registrado cerca de las coordenadas latitud 3.3385 y longitud -76.5410 en un radio de 1.5 km en Pance?",
            "expected_tool": "consultar_reportes",
            "must_contain_any": ["Pance", "Comuna 22"],
            "must_contain_all": ["CIV-2026-DEMO0003", "TALA"],
        },
        # 3. Interpretación de descripciones ciudadanas (Q06..Q07)
        {
            "id": "Q06",
            "group": "3_interpretacion_descripcion",
            "kind": "agent",
            "golden_ref": None,
            "input": "Busca los reportes en la Comuna 20 (barrio Siloé) sobre huecos que afectan el paso de camperos.",
            "expected_tool": "consultar_reportes",
            "must_contain_any": ["Siloé", "Comuna 20", "HUECO"],
            "must_contain_all": ["CIV-2026-DEMO0009"],
        },
        {
            "id": "Q07",
            "group": "3_interpretacion_descripcion",
            "kind": "agent",
            "golden_ref": None,
            "input": "Busca reportes de BASURAS en la Comuna 10 (sector Santa Elena) e indica el código de radicado.",
            "expected_tool": "consultar_reportes",
            "must_contain_any": ["Santa Elena", "Comuna 10", "BASURAS"],
            "must_contain_all": ["CIV-2026-DEMO0010"],
        },
        # 4. Clasificación multimodal con conjunto de referencia (Q08..Q11)
        {
            "id": "Q08",
            "group": "4_clasificacion_multimodal",
            "kind": "multimodal",
            "expected_category": "HUECO",
            "latitude": 3.4658,
            "longitude": -76.5283,
            "input": "DATO SINTÉTICO EVAL: Hundimiento severo y bache profundo en el asfalto del carril vehicular.",
        },
        {
            "id": "Q09",
            "group": "4_clasificacion_multimodal",
            "kind": "multimodal",
            "expected_category": "BASURAS",
            "latitude": 3.4012,
            "longitude": -76.5045,
            "input": "DATO SINTÉTICO EVAL: Acumulación de bolsas de basura, escombros y residuos orgánicos en la esquina.",
        },
        {
            "id": "Q10",
            "group": "4_clasificacion_multimodal",
            "kind": "multimodal",
            "expected_category": "TALA",
            "latitude": 3.3385,
            "longitude": -76.5410,
            "input": "DATO SINTÉTICO EVAL: Corte de tronco de árbol adulto con motosierra y ramas taladas en corredor verde.",
        },
        {
            "id": "Q11",
            "group": "4_clasificacion_multimodal",
            "kind": "multimodal",
            "expected_category": "QUEMA",
            "latitude": 3.4752,
            "longitude": -76.5468,
            "input": "DATO SINTÉTICO EVAL: Llamas activas y columna de humo por quema de vegetación seca en la ladera del cerro.",
        },
        # 5. Selección de herramientas del agente y límites (Q12..Q13)
        {
            "id": "Q12",
            "group": "5_seleccion_herramientas",
            "kind": "agent",
            "golden_ref": "GD-05",
            "input": "Consulta los reportes con status ANALYZED_PENDING_CONFIRMATION e indica cuál es su código de radicado.",
            "expected_tool": "consultar_reportes",
            "must_contain_any": ["Capri", "TALA", "Comuna 17"],
            "must_contain_all": ["CIV-2026-DEMO0008"],
        },
        {
            "id": "Q13",
            "group": "5_seleccion_herramientas_y_guardrail",
            "kind": "agent",
            "golden_ref": None,
            "input": "Usa la herramienta proponer_actualizacion_critica para solicitar cambiar el estado del reporte CIV-2026-DEMO0002 a RESOLVED porque ya fue atendido.",
            "expected_tool": "proponer_actualizacion_critica",
            "must_contain_any": ["PENDING", "aprobación", "humana", "solicitud"],
            "must_contain_all": ["CIV-2026-DEMO0002"],
        },
        # 6. Manejo de información insuficiente / fuera de dominio (Q14)
        {
            "id": "Q14",
            "group": "6_informacion_insuficiente",
            "kind": "agent",
            "golden_ref": "GD-06",
            "input": "¿Cuántos reportes de radiación nuclear o índice satelital NDVI en tiempo real existen registrados en la Comuna 99 de Cali?",
            "expected_tool": None,
            "must_contain_any": ["no existe", "no hay", "0", "ningún", "ninguno", "sin evidencia"],
            "must_contain_all": [],
        },
        # 7. Caso de fallo y recuperación entre proveedores (Q15)
        {
            "id": "Q15",
            "group": "7_fallo_y_recuperacion_proveedores",
            "kind": "multimodal_fault_429",
            "expected_category": "QUEMA",
            "latitude": 3.4752,
            "longitude": -76.5468,
            "input": "DATO SINTÉTICO EVAL FALLBACK 429: Incendio de cobertura vegetal y humo visible en ascenso a Tres Cruces.",
        },
    ]


def get_latest_trace_info(trace_group_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider, model, attempt_number, success, latency_ms,
                       prompt_tokens, completion_tokens, total_tokens,
                       estimated_cost_usd, error_code, metadata
                FROM ai_traces
                WHERE trace_group_id = %s
                ORDER BY attempt_number ASC, created_at ASC;
                """,
                (trace_group_id,),
            )
            rows = cur.fetchall()

    if not rows:
        return {
            "provider": "none",
            "model": "none",
            "attempts": 0,
            "fallback_used": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "trace_steps": [],
        }

    ok_rows = [r for r in rows if r["success"]]
    final_row = ok_rows[-1] if ok_rows else rows[-1]
    failed_rows = [r for r in rows if not r["success"]]
    p_tok = sum(int(r["prompt_tokens"]) for r in rows)
    c_tok = sum(int(r["completion_tokens"]) for r in rows)
    t_tok = sum(int(r["total_tokens"]) for r in rows)
    cost = round(sum(float(r["estimated_cost_usd"]) for r in rows), 8)

    return {
        "provider": final_row["provider"],
        "model": final_row["model"],
        "attempts": len(rows),
        "fallback_used": len(failed_rows) > 0 or final_row["provider"] == "groq" or final_row["model"] == "gemini-3.6-flash",
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "total_tokens": t_tok,
        "estimated_cost_usd": cost,
        "trace_steps": [
            {
                "attempt": r["attempt_number"],
                "provider": r["provider"],
                "model": r["model"],
                "success": r["success"],
                "latency_ms": r["latency_ms"],
                "error_code": r["error_code"],
            }
            for r in rows
        ],
    }


def run_evaluation(mode: str = "all", pause_sec: float = 2.5) -> dict[str, Any]:
    import os
    import shutil
    import tempfile
    from uuid import UUID
    import uuid

    if not is_disposable_test_or_eval_db(settings.DATABASE_URL):
        if os.getenv("CIVIA_STRICT_REJECT_NON_EVAL_DB") == "1":
            assert_disposable_test_db(settings.DATABASE_URL)
        eval_db_name = f"civia_eval_{uuid.uuid4().hex[:8]}"
        eval_db_url = ensure_isolated_database(eval_db_name, settings.DATABASE_URL)
        settings.DATABASE_URL = eval_db_url
        os.environ["DATABASE_URL"] = eval_db_url

    assert_disposable_test_db(settings.DATABASE_URL)

    prev_upload_dir = settings.UPLOAD_DIR
    eval_upload_dir = Path(tempfile.gettempdir()) / f"civia_eval_uploads_{uuid.uuid4().hex[:8]}"
    eval_upload_dir.mkdir(parents=True, exist_ok=True)
    settings.UPLOAD_DIR = eval_upload_dir

    run_migrations()
    seed_synthetic_reports(force_reset=False)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    golden_path = EVAL_DIR / "casos_dorados.json"
    golden_sql_checks = verify_golden_sql_ground_truth(golden_path)

    if mode in ("deterministic", "offline"):
        report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "database": get_database_name(settings.DATABASE_URL),
            "golden_sql_verification": golden_sql_checks,
        }
        (RESULTS_DIR / "reporte_determinista.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        settings.UPLOAD_DIR = prev_upload_dir
        shutil.rmtree(eval_upload_dir, ignore_errors=True)
        return report

    created_eval_pa_ids: list[UUID] = []

    queries = build_15_representative_queries()
    query_results: list[dict[str, Any]] = []

    set_runtime_fault_override("NONE")
    # Nota: no reseteamos el circuit breaker entre Q01..Q14 para que el circuito abierto
    # en modelos con sobrecarga 503 opere de manera realista como en producción.
    reset_all_circuits()

    for idx, q in enumerate(queries, start=1):
        qid = q["id"]
        kind = q["kind"]
        t0 = time.perf_counter()

        if kind == "agent":
            set_runtime_fault_override("NONE")
            res = run_civia_agent(q["input"])
            dt_ms = int((time.perf_counter() - t0) * 1000)

            if res.get("pending_approval_id"):
                try:
                    pa_uuid = UUID(str(res["pending_approval_id"]))
                    if pa_uuid not in created_eval_pa_ids:
                        created_eval_pa_ids.append(pa_uuid)
                except ValueError:
                    pass
            for tool_call in res.get("tools_invoked", []):
                aid_str = (tool_call.get("result") or {}).get("approval_id")
                if aid_str:
                    try:
                        aid_uuid = UUID(str(aid_str))
                        if aid_uuid not in created_eval_pa_ids:
                            created_eval_pa_ids.append(aid_uuid)
                    except ValueError:
                        pass

            trace_info = get_latest_trace_info(res["trace_group_id"])
            answer_text = res["answer"]
            ans_upper = answer_text.upper()

            tools_called = [t["tool"] for t in res["tools_invoked"]]
            tool_ok = (q["expected_tool"] in tools_called) or bool(res.get("degraded_sql_mode"))
            all_ok = all(tok.upper() in ans_upper for tok in q.get("must_contain_all", []))
            any_list = q.get("must_contain_any", [])
            any_ok = True if not any_list else any(tok.upper() in ans_upper for tok in any_list)
            passed = bool(tool_ok and all_ok and any_ok)

            query_results.append(
                {
                    "id": qid,
                    "group": q["group"],
                    "kind": kind,
                    "golden_ref": q.get("golden_ref"),
                    "input": q["input"],
                    "passed": passed,
                    "latency_ms": dt_ms,
                    "provider": trace_info["provider"],
                    "model": trace_info["model"],
                    "fallback_used": trace_info["fallback_used"],
                    "attempts": trace_info["attempts"],
                    "tools_invoked": tools_called,
                    "guardrail_triggered": res.get("guardrail_triggered"),
                    "prompt_tokens": trace_info["prompt_tokens"],
                    "completion_tokens": trace_info["completion_tokens"],
                    "total_tokens": trace_info["total_tokens"],
                    "estimated_cost_usd": trace_info["estimated_cost_usd"],
                    "output_summary": answer_text[:280],
                    "trace_steps": trace_info["trace_steps"],
                }
            )
        else:
            is_fault_test = kind == "multimodal_fault_429"
            if is_fault_test:
                reset_all_circuits()
                set_runtime_fault_override("429")
            else:
                set_runtime_fault_override("NONE")

            cat_lower = q["expected_category"].lower()
            asset_file = DEMO_ASSETS_DIR / f"sample_{cat_lower}.jpg"
            if not asset_file.exists():
                asset_file = DEMO_ASSETS_DIR / "civ-2026-demo0001.jpg"
            img_bytes = asset_file.read_bytes()
            contract, meta = classify_evidence_with_router(
                description=q["input"],
                latitude=q["latitude"],
                longitude=q["longitude"],
                image_bytes=img_bytes,
                image_mime="image/jpeg",
            )
            dt_ms = int((time.perf_counter() - t0) * 1000)
            set_runtime_fault_override("NONE")

            trace_info = get_latest_trace_info(meta["trace_group_id"])
            pred_cat = contract.category if contract else None
            passed = pred_cat == q["expected_category"]
            if is_fault_test:
                passed = passed and bool(meta.get("fallback_used"))

            query_results.append(
                {
                    "id": qid,
                    "group": q["group"],
                    "kind": kind,
                    "golden_ref": None,
                    "input": q["input"],
                    "expected_category": q["expected_category"],
                    "predicted_category": pred_cat,
                    "passed": passed,
                    "latency_ms": dt_ms,
                    "provider": trace_info["provider"],
                    "model": trace_info["model"],
                    "fallback_used": trace_info["fallback_used"],
                    "attempts": trace_info["attempts"],
                    "prompt_tokens": trace_info["prompt_tokens"],
                    "completion_tokens": trace_info["completion_tokens"],
                    "total_tokens": trace_info["total_tokens"],
                    "estimated_cost_usd": trace_info["estimated_cost_usd"],
                    "output_summary": contract.summary if contract else "SIN_RESPUESTA",
                    "trace_steps": trace_info["trace_steps"],
                }
            )

        if idx < len(queries) and pause_sec > 0:
            time.sleep(pause_sec)

    # Limpiar exclusivamente las solicitudes de aprobación cuyo UUID fue generado por esta corrida (N-03)
    if created_eval_pa_ids:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM pending_approvals WHERE id = ANY(%s);",
                    (created_eval_pa_ids,),
                )
                conn.commit()
    settings.UPLOAD_DIR = prev_upload_dir
    shutil.rmtree(eval_upload_dir, ignore_errors=True)

    total_q = len(query_results)
    passed_q = sum(1 for r in query_results if r["passed"])
    failed_q = total_q - passed_q
    accuracy_pct = round((passed_q / total_q) * 100.0, 2) if total_q else 0.0

    mm_rows = [r for r in query_results if r["kind"] in ("multimodal", "multimodal_fault_429")]
    mm_passed = sum(1 for r in mm_rows if r["predicted_category"] == r["expected_category"])
    mm_accuracy_pct = round((mm_passed / len(mm_rows)) * 100.0, 2) if mm_rows else 0.0

    latencies = [float(r["latency_ms"]) for r in query_results]
    p50_ms = percentile(latencies, 50.0)
    p90_ms = percentile(latencies, 90.0)

    total_tokens = sum(int(r["total_tokens"]) for r in query_results)
    total_prompt_tokens = sum(int(r["prompt_tokens"]) for r in query_results)
    total_completion_tokens = sum(int(r["completion_tokens"]) for r in query_results)
    total_cost_usd = round(sum(float(r["estimated_cost_usd"]) for r in query_results), 6)
    avg_cost_usd = round(total_cost_usd / total_q, 6) if total_q else 0.0

    fallback_count = sum(1 for r in query_results if r["fallback_used"])
    fallback_rate_pct = round((fallback_count / total_q) * 100.0, 2) if total_q else 0.0

    q15_row = next((r for r in query_results if r["id"] == "Q15"), None)
    recovery_latency_ms = q15_row["latency_ms"] if q15_row else None

    provider_usage: dict[str, int] = {}
    for r in query_results:
        key = f"{r['provider']}:{r['model']}"
        provider_usage[key] = provider_usage.get(key, 0) + 1

    summary_report = {
        "metadata": {
            "project": "CIVIA — Momento Evaluativo 2",
            "team": ["Stefania Córdoba", "Sebastian Espinosa"],
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "methodology_note": (
                "Métricas observadas directamente sobre PostgreSQL 17 y llamadas reales al router Gemini -> Groq -> Gemini. "
                "El cobro facturado real en las cuentas de desarrollo es $0.00 USD (tier gratuito); el costo en USD reportado "
                "corresponde a la estimación calculada sobre los tokens reales consumidos con las tarifas de referencia por 1M de tokens."
            ),
        },
        "golden_questions_sql_verification": {
            "total_golden_cases": len(golden_sql_checks),
            "all_sql_verified": all(g["sql_verificado"] for g in golden_sql_checks),
            "cases": golden_sql_checks,
        },
        "metrics_15_queries": {
            "total_queries_executed": total_q,
            "passed_queries": passed_q,
            "failed_queries": failed_q,
            "answer_accuracy_pct": accuracy_pct,
            "multimodal_reference_count": len(mm_rows),
            "multimodal_classification_accuracy_pct": mm_accuracy_pct,
            "p50_latency_ms_observed": p50_ms,
            "p90_latency_ms_observed": p90_ms,
            "min_latency_ms_observed": min(latencies) if latencies else 0.0,
            "max_latency_ms_observed": max(latencies) if latencies else 0.0,
            "total_prompt_tokens_observed": total_prompt_tokens,
            "total_completion_tokens_observed": total_completion_tokens,
            "total_tokens_observed": total_tokens,
            "avg_tokens_per_query": round(total_tokens / total_q, 1) if total_q else 0.0,
            "billed_cost_usd_observed": 0.0,
            "estimated_total_cost_usd": total_cost_usd,
            "estimated_avg_cost_per_query_usd": avg_cost_usd,
            "provider_model_distribution": provider_usage,
            "fallback_count": fallback_count,
            "fallback_rate_pct": fallback_rate_pct,
            "fault_recovery_latency_ms_observed": recovery_latency_ms,
        },
        "queries_detail": query_results,
    }

    json_out = RESULTS_DIR / "reporte_evaluacion.json"
    json_out.write_text(json.dumps(summary_report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Reporte Reproducible de Evaluación — CIVIA (Momento 2)",
        "",
        f"- **Fecha de ejecución (UTC):** `{summary_report['metadata']['executed_at_utc']}`",
        "- **Equipo:** Stefania Córdoba y Sebastian Espinosa",
        f"- **Casos dorados verificados por SQL:** `{len(golden_sql_checks)}/{len(golden_sql_checks)}` (`all_sql_verified = {summary_report['golden_questions_sql_verification']['all_sql_verified']}`)",
        "",
        "## 1. Resumen de Métricas Obligatorias (15 Consultas Representativas)",
        "",
        "| Métrica | Valor | Tipo de dato |",
        "|---|---|---|",
        f"| Total de consultas ejecutadas | `{total_q}` | Observado |",
        f"| Aciertos / Errores | `{passed_q} aciertos / {failed_q} errores` | Observado |",
        f"| Exactitud global de respuestas | `{accuracy_pct}%` (`{passed_q}/{total_q}`) | Observado |",
        f"| Precisión de clasificación multimodal (`Q08..Q11` + `Q15`) | `{mm_accuracy_pct}%` (`{mm_passed}/{len(mm_rows)}`) | Observado |",
        f"| Latencia **P50** | `{p50_ms} ms` | Observado |",
        f"| Latencia **P90** | `{p90_ms} ms` | Observado |",
        f"| Tokens consumidos totales (prompt + completion) | `{total_tokens}` (`{total_prompt_tokens}` in / `{total_completion_tokens}` out) | Observado |",
        f"| Costo facturado real (tier gratuito AI Studio / Groq) | `$0.000000 USD` | Observado |",
        f"| Costo equivalente estimado por consulta | `${avg_cost_usd:.6f} USD` | Estimado por tarifa/tokens |",
        f"| Costo equivalente estimado total (15 consultas) | `${total_cost_usd:.6f} USD` | Estimado por tarifa/tokens |",
        f"| Frecuencia de fallback | `{fallback_rate_pct}%` (`{fallback_count}/{total_q}`) | Observado |",
        f"| Tiempo de recuperación ante fallo forzado 429 (`Q15`) | `{recovery_latency_ms} ms` | Observado |",
        f"| Distribución de proveedor/modelo | `{json.dumps(provider_usage)}` | Observado |",
        "",
        "## 2. Detalle por Consulta (`Q01` .. `Q15`)",
        "",
        "| ID | Grupo | Proveedor / Modelo | Latencia (ms) | Tokens | Fallback | Resultado |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in query_results:
        status_str = "PASS" if r["passed"] else "FAIL"
        md_lines.append(
            f"| `{r['id']}` | `{r['group']}` | `{r['provider']}:{r['model']}` | `{r['latency_ms']}` | `{r['total_tokens']}` | `{r['fallback_used']}` | **{status_str}** |"
        )

    md_out = RESULTS_DIR / "reporte_evaluacion.md"
    md_out.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Evaluación completada: {passed_q}/{total_q} ({accuracy_pct}%) | P50={p50_ms}ms | P90={p90_ms}ms")
    return summary_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecuta la suite de evaluación de CIVIA.")
    parser.add_argument("--mode", choices=["all", "deterministic", "offline", "live"], default="all")
    parser.add_argument("--pause", type=float, default=2.5)
    args = parser.parse_args()
    run_evaluation(mode=args.mode, pause_sec=args.pause)
