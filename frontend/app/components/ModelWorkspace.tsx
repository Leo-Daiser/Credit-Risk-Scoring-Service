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
  formatPercent,
} from "../lib/api";

export function ModelWorkspace() {
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [schema, setSchema] = useState<FeatureSchema | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<ModelInfo>("model_info"),
      apiFetch<FeatureSchema>("feature_schema"),
    ])
      .then(([modelInfo, featureSchema]) => {
        setModel(modelInfo);
        setSchema(featureSchema);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <div className="page-stack">
      <section className="model-hero">
        <div>
          <span className="section-kicker light">Production model bundle</span>
          <h2>Версия модели — часть каждого решения.</h2>
          <p>
            Контракт, калибровка, порог, risk bands и reference statistics упакованы вместе.
            API и worker загружают один и тот же доверенный artifact.
          </p>
          <div className="model-version-line">
            <span className="status-badge success"><CheckCircle2 size={14} /> acceptance {model?.acceptance_status ?? "—"}</span>
            <code>{model?.model_version ?? "production bundle unavailable"}</code>
          </div>
        </div>
        <div className="bundle-visual" aria-hidden="true">
          <span>FEATURES</span><span>MODEL</span><span>THRESHOLD</span><span>REFERENCE</span>
          <div><Boxes size={34} /><strong>immutable</strong><small>bundle</small></div>
        </div>
      </section>

      {error ? <div className="form-error" role="alert"><TriangleAlert size={18} /> {error}</div> : null}

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
            <div><span className="section-kicker">Runtime topology</span><h3>Три осмысленных сервиса</h3></div>
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
    </div>
  );
}
