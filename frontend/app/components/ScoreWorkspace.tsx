"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Braces,
  CheckCircle2,
  CircleGauge,
  FileJson,
  Gauge,
  LoaderCircle,
  ScanLine,
  ShieldCheck,
} from "lucide-react";
import {
  apiFetch,
  type FeatureSchema,
  type ScoreResult,
  formatPercent,
} from "../lib/api";

const initialPayload = `{
  "AMT_INCOME_TOTAL": 180000,
  "AMT_CREDIT": 450000,
  "AMT_ANNUITY": 24000,
  "AGE_YEARS": 36,
  "NAME_CONTRACT_TYPE": "Cash loans",
  "EXT_SOURCE_2": 0.61,
  "EXT_SOURCE_3": 0.48
}`;

export function ScoreWorkspace() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [schema, setSchema] = useState<FeatureSchema | null>(null);
  const [payload, setPayload] = useState(initialPayload);
  const [requestId, setRequestId] = useState("");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiFetch<FeatureSchema>("feature_schema")
      .then(setSchema)
      .catch((reason: Error) => setError(reason.message));
  }, []);

  const loadJson = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      setPayload(await file.text());
      setError(null);
    } catch {
      setError("Не удалось прочитать JSON-файл.");
    }
  };

  const submit = async () => {
    setError(null);
    setResult(null);
    let features: Record<string, string | number | boolean | null>;
    try {
      const parsed = JSON.parse(payload) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Ожидается JSON-объект признаков.");
      }
      features = parsed as Record<string, string | number | boolean | null>;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Некорректный JSON.");
      return;
    }

    setLoading(true);
    try {
      const score = await apiFetch<ScoreResult>("score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: requestId.trim() || undefined,
          features,
        }),
      });
      setResult(score);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="page-intro score-intro">
        <div>
          <span className="section-kicker">Одна заявка · один audit ID</span>
          <h2>Проверьте риск до принятия решения.</h2>
          <p>
            Передайте полный объект подготовленных признаков. Сервис проверит контракт,
            оценит качество входа и вернёт калиброванную вероятность с факторами риска.
          </p>
        </div>
        <div className="schema-summary">
          <span>Текущий контракт</span>
          <strong>{schema?.feature_count ?? "—"} признаков</strong>
          <small>
            минимальное покрытие {schema ? formatPercent(schema.min_feature_coverage, 0) : "—"}
          </small>
        </div>
      </section>

      <section className="score-layout">
        <article className="score-form panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">Feature payload</span>
              <h3>Данные заявки</h3>
            </div>
            <button className="button button-mini" type="button" onClick={() => fileRef.current?.click()}>
              <FileJson size={16} /> Из JSON
            </button>
            <input ref={fileRef} type="file" accept="application/json,.json" onChange={loadJson} hidden />
          </div>

          <label className="field-label" htmlFor="request-id">
            Request ID <span className="optional">необязательно</span>
            <input
              id="request-id"
              value={requestId}
              onChange={(event) => setRequestId(event.target.value)}
              placeholder="например, application-2026-0042"
              maxLength={128}
              spellCheck={false}
            />
          </label>

          <label className="field-label" htmlFor="feature-json">
            JSON с признаками
            <textarea
              id="feature-json"
              className="json-editor"
              value={payload}
              onChange={(event) => setPayload(event.target.value)}
              spellCheck={false}
              rows={13}
            />
          </label>

          <div className="editor-note">
            <Braces size={17} />
            <span>
              Пример соответствует локальному bundle из README. Для другой версии используйте
              её feature schema или выгрузку build-full-features.
            </span>
          </div>

          {error ? (
            <div className="form-error" role="alert">
              <AlertTriangle size={18} /> {error}
            </div>
          ) : null}

          <button className="button button-dark button-full" type="button" onClick={submit} disabled={loading}>
            {loading ? <LoaderCircle className="spin" size={18} /> : <ScanLine size={18} />}
            {loading ? "Рассчитываем…" : "Рассчитать риск"}
            {!loading ? <ArrowRight size={18} /> : null}
          </button>
        </article>

        <aside className={`score-result ${result ? "has-result" : ""}`}>
          {result ? (
            <>
              <div className="result-header">
                <span className={`result-decision ${result.decision}`}>
                  {result.decision === "approve" ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
                  {result.decision === "approve" ? "Одобрить" : "Отказать"}
                </span>
                <span className="mono result-id">{result.request_id}</span>
              </div>

              <div className={`probability-ring ${result.decision}`} style={{ "--probability": `${Math.round(result.default_probability * 100)}%` } as React.CSSProperties}>
                <div>
                  <strong>{formatPercent(result.default_probability, 2)}</strong>
                  <span>вероятность дефолта</span>
                </div>
              </div>

              <div className="result-facts">
                <div><span>Риск-группа</span><strong>{result.risk_band}</strong></div>
                <div><span>Порог решения</span><strong>{formatPercent(result.decision_threshold, 0)}</strong></div>
                <div><span>Latency</span><strong>{result.latency_ms.toFixed(0)} ms</strong></div>
              </div>

              <div className="quality-block">
                <div className="quality-head">
                  <span>Качество входа</span>
                  <strong>{formatPercent(result.input_quality.supplied_feature_coverage, 0)}</strong>
                </div>
                <div className="quality-track"><i style={{ width: `${result.input_quality.supplied_feature_coverage * 100}%` }} /></div>
                <small>{result.missing_feature_count} пропущенных признаков</small>
              </div>

              <div className="reasons-block">
                <span className="section-kicker">Факторы повышенного риска</span>
                {result.reason_codes.length ? result.reason_codes.map((reason) => (
                  <div className="reason-row" key={`${reason.code}-${reason.contribution}`}>
                    <Gauge size={17} />
                    <div><strong>{reason.feature}</strong><span>{reason.description}</span></div>
                  </div>
                )) : <p className="muted">Положительные reason codes не найдены.</p>}
              </div>
            </>
          ) : (
            <div className="result-placeholder">
              <div className="placeholder-symbol"><CircleGauge size={35} /></div>
              <span className="section-kicker">Результат</span>
              <h3>Здесь появится решение</h3>
              <p>
                Вероятность дефолта, риск-группа, качество входа и локальные факторы будут
                показаны после успешной проверки payload.
              </p>
              <div className="placeholder-contract">
                <ShieldCheck size={18} />
                <span>Ответ будет записан в PostgreSQL audit log</span>
              </div>
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}
