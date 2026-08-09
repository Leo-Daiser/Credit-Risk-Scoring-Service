"use client";

import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  Boxes,
  CheckCircle2,
  Database,
  FileCheck2,
  ServerCog,
  ShieldCheck,
  TriangleAlert,
  Workflow,
} from "lucide-react";
import {
  apiFetch,
  type FeatureSchema,
  type ModelInfo,
  type RuntimeStatus,
  formatPercent,
} from "../lib/api";

export function ModelWorkspace() {
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [schema, setSchema] = useState<FeatureSchema | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([
      apiFetch<RuntimeStatus>("v1/runtime/status"),
      apiFetch<ModelInfo>("model_info"),
      apiFetch<FeatureSchema>("feature_schema"),
    ])
      .then(([runtimeResult, modelResult, schemaResult]) => {
        if (runtimeResult.status === "fulfilled") setRuntime(runtimeResult.value);
        if (modelResult.status === "fulfilled") setModel(modelResult.value);
        if (schemaResult.status === "fulfilled") setSchema(schemaResult.value);
        if (runtimeResult.status === "rejected") throw runtimeResult.reason;
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <div className="page-stack">
      <section className="model-hero">
        <div>
          <span className="section-kicker light">Состояние системы</span>
          <h2>Расчётный модуль и внутренние сервисы.</h2>
          <p>
            Здесь сотрудники могут проверить версию расчётного модуля, готовность
            внутренних операций и совместимость загружаемых данных.
          </p>
          <div className="model-version-line">
            <span className="status-badge success"><CheckCircle2 size={14} /> acceptance {model?.acceptance_status ?? "—"}</span>
            <code>{model?.model_version ?? "расчётный модуль недоступен"}</code>
          </div>
        </div>
        <div className="bundle-visual" aria-hidden="true">
          <span>ДАННЫЕ</span><span>РАСЧЁТ</span><span>ПРАВИЛА</span><span>КОНТРОЛЬ</span>
          <div><Boxes size={34} /><strong>внутренний</strong><small>модуль</small></div>
        </div>
      </section>

      {error ? <div className="form-error" role="alert"><TriangleAlert size={18} /> {error}</div> : null}

      <section className="model-metrics runtime-model-grid">
        <article><span>Riskline Public Profile Model</span><strong>{runtime?.public_model_available ? "ACTIVE" : "PUBLIC ML INACTIVE"}</strong><small>{runtime?.public_model_version ?? "rules fallback"}</small></article>
        <article><span>Full Credit Risk Model</span><strong>{runtime?.full_model_available ? "ACTIVE" : "MISSING"}</strong><small>внутренний B2B-контур</small></article>
        <article><span>Offer Outcome Ranker</span><strong>{runtime?.offer_ranker_available ? "ML AVAILABLE" : "RULES MODE"}</strong><small>нет обучения на демо-событиях партнёров</small></article>
        <article><span>Fallback профилей</span><strong>{formatPercent(runtime?.public_model_fallback_rate ?? null, 0)}</strong><small>{runtime?.public_model_scoring_volume ?? 0} из {runtime?.public_profile_scores ?? 0} с публичной моделью</small></article>
      </section>

      <details className="panel system-technical-details">
        <summary>Технические детали</summary>
      <section className="model-metrics">
        <article><span>ROC-AUC</span><strong>{model?.metrics.roc_auc != null ? Number(model.metrics.roc_auc).toFixed(5) : "—"}</strong><small>локальный evaluation split</small></article>
        <article><span>PR-AUC</span><strong>{model?.metrics.pr_auc != null ? Number(model.metrics.pr_auc).toFixed(5) : "—"}</strong><small>локальный evaluation split</small></article>
        <article><span>Brier score</span><strong>{model?.metrics.brier_score != null ? Number(model.metrics.brier_score).toFixed(5) : "—"}</strong><small>после калибровки</small></article>
        <article><span>Decision threshold</span><strong>{formatPercent(model?.decision_threshold ?? null, 0)}</strong><small>зафиксирован в bundle</small></article>
      </section>

      <section className="model-grid">
        <article className="panel contract-panel" id="contract">
          <div className="panel-heading">
            <div><span className="section-kicker">Input contract</span><h3>Что можно загружать</h3></div>
            <FileCheck2 size={25} />
          </div>
          <p>
            Только таблицу после проектного feature pipeline. В первой колонке — уникальный
            ID, далее признаки с именами из схемы production bundle.
          </p>
          <div className="contract-numbers">
            <div><span>Всего</span><strong>{schema?.feature_count ?? "—"}</strong><small>признаков</small></div>
            <div><span>Числовых</span><strong>{schema?.numeric_features.length ?? "—"}</strong><small>columns</small></div>
            <div><span>Категориальных</span><strong>{schema?.categorical_features.length ?? "—"}</strong><small>columns</small></div>
          </div>
          <div className="contract-rules">
            <span><ShieldCheck size={17} /> unknown columns отклоняются</span>
            <span><ShieldCheck size={17} /> required fields проверяются</span>
            <span><ShieldCheck size={17} /> coverage ≥ {schema ? formatPercent(schema.min_feature_coverage, 0) : "—"}</span>
          </div>
          <a className="button button-soft" href="/api/backend/v1/batch/template.csv">
            <ArrowDownToLine size={17} /> Скачать CSV-заголовок
          </a>
        </article>

        <article className="panel architecture-panel">
          <div className="panel-heading">
            <div><span className="section-kicker">Операционный контур</span><h3>Внутренние сервисы</h3></div>
            <Workflow size={25} />
          </div>
          <div className="service-map">
            <div className="service-node web"><span>01</span><strong>Web / BFF</strong><small>UX и server-side API key</small></div>
            <i>→</i>
            <div className="service-node api"><span>02</span><strong>Scoring API</strong><small>контракты и online inference</small></div>
            <i>→</i>
            <div className="service-node worker"><span>03</span><strong>Batch worker</strong><small>durable DB queue</small></div>
          </div>
          <div className="shared-layer">
            <Database size={20} />
            <div><strong>PostgreSQL + artifact volume</strong><span>audit, jobs, model registry, result files</span></div>
          </div>
          <p className="architecture-note">
            ML-код остаётся общей библиотекой внутри Python image: это исключает расхождение
            online и batch inference, но процессы масштабируются независимо.
          </p>
        </article>
      </section>

      <section className="boundary-grid">
        <article><ServerCog size={21} /><div><strong>API не считает batch внутри HTTP</strong><span>Запрос только сохраняет файл и durable job.</span></div></article>
        <article><Database size={21} /><div><strong>Файл не хранится в базе</strong><span>PostgreSQL содержит метаданные, не бинарные данные.</span></div></article>
        <article><ShieldCheck size={21} /><div><strong>Секрет не попадает в браузер</strong><span>BFF добавляет API key на серверной стороне.</span></div></article>
      </section>
      </details>
    </div>
  );
}
