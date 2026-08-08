"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronRight,
  CircleGauge,
  FileUp,
  Gauge,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import {
  apiFetch,
  type DashboardData,
  formatDate,
  formatPercent,
} from "../lib/api";

function shortVersion(version?: string): string {
  if (!version) return "модель не подключена";
  const [name, hash] = version.split(/-(?=[^-]+$)/);
  return `${name.replaceAll("_", " ")} · ${hash ?? "versioned"}`;
}

export function DashboardClient() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<DashboardData>("v1/dashboard")
      .then((payload) => {
        if (active) setData(payload);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, []);

  const runningJobs = (data?.batches.queued ?? 0) + (data?.batches.running ?? 0);
  const healthLabel = data ? "Готов к решениям" : error ? "Нет связи с API" : "Проверяем контур";

  return (
    <div className="dashboard-stack">
      <section className="hero-grid">
        <article className="hero-card">
          <div className="hero-content">
            <span className="section-kicker">
              <Sparkles size={15} aria-hidden="true" />
              Новый рабочий день
            </span>
            <h2>
              Решения по риску —
              <br />
              <em>без ручной сверки.</em>
            </h2>
            <p>
              Оцените одну заявку или отправьте подготовленный реестр. Версия модели,
              качество входа и результат фиксируются в аудите.
            </p>
            <div className="hero-actions">
              <Link className="button button-dark" href="/score">
                Оценить заявку
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link className="button button-ghost" href="/batches">
                <FileUp size={18} aria-hidden="true" />
                Загрузить реестр
              </Link>
            </div>
          </div>

          <div className="hero-signal" aria-label={`Состояние модели: ${healthLabel}`}>
            <div className={`signal-orbit ${data ? "is-ready" : error ? "is-error" : ""}`}>
              <div className="signal-core">
                <ShieldCheck size={30} strokeWidth={1.6} aria-hidden="true" />
                <strong>{data?.model.feature_count ?? "—"}</strong>
                <span>признаков</span>
              </div>
            </div>
            <div className="signal-copy">
              <span className={`live-dot ${error ? "is-error" : ""}`} />
              <div>
                <strong>{healthLabel}</strong>
                <small>{shortVersion(data?.model.model_version)}</small>
              </div>
            </div>
          </div>
        </article>

        <aside className="day-card">
          <div className="day-card-head">
            <span>Сегодня</span>
            <CircleGauge size={21} aria-hidden="true" />
          </div>
          <strong className="day-number">{data?.scoring.last_24h ?? "—"}</strong>
          <span className="day-label">решений за 24 часа</span>
          <div className="day-divider" />
          <div className="day-stat">
            <span>В очереди</span>
            <strong>{runningJobs}</strong>
          </div>
          <div className="day-stat">
            <span>Ошибки jobs</span>
            <strong className={data?.batches.failed ? "text-danger" : ""}>
              {data?.batches.failed ?? "—"}
            </strong>
          </div>
          <Link href="/batches" className="inline-link">
            Открыть очередь <ChevronRight size={16} aria-hidden="true" />
          </Link>
        </aside>
      </section>

      {error ? (
        <div className="connection-banner" role="status">
          <RotateCcw size={18} aria-hidden="true" />
          <div>
            <strong>Интерфейс доступен, backend не ответил.</strong>
            <span>{error}</span>
          </div>
        </div>
      ) : null}

      <section className="metric-grid" aria-label="Ключевые показатели">
        <article className="metric-card">
          <div className="metric-icon mint"><Check size={19} aria-hidden="true" /></div>
          <span>Доля одобрений</span>
          <strong>{formatPercent(data?.scoring.approval_rate ?? null)}</strong>
          <small>по решениям с сохранённым исходом</small>
        </article>
        <article className="metric-card">
          <div className="metric-icon lime"><Gauge size={19} aria-hidden="true" /></div>
          <span>Средняя вероятность PD</span>
          <strong>{formatPercent(data?.scoring.mean_default_probability ?? null)}</strong>
          <small>по накопленной истории</small>
        </article>
        <article className="metric-card metric-wide">
          <div className="metric-topline">
            <div>
              <span>Проверок всего</span>
              <strong>{data?.scoring.total ?? "—"}</strong>
            </div>
            <span className="metric-chip">audit log</span>
          </div>
          <div className="risk-stripe" aria-hidden="true">
            <i className="risk-low" />
            <i className="risk-medium" />
            <i className="risk-high" />
          </div>
          <div className="risk-legend">
            {Object.entries(data?.scoring.risk_bands ?? {}).length ? (
              Object.entries(data?.scoring.risk_bands ?? {}).map(([name, count]) => (
                <span key={name}>{name}: {count}</span>
              ))
            ) : (
              <span>Распределение появится после первых решений</span>
            )}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="panel recent-panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">Последние решения</span>
              <h3>Журнал скоринга</h3>
            </div>
            <Link className="inline-link" href="/history">
              Вся история <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>

          <div className="decision-list">
            {data?.recent_decisions.length ? (
              data.recent_decisions.map((item) => (
                <div className="decision-row" key={item.request_id}>
                  <span className={`decision-mark ${item.decision ?? "unknown"}`} />
                  <div className="decision-id">
                    <strong>{item.request_id}</strong>
                    <small>{formatDate(item.received_at)}</small>
                  </div>
                  <span className="risk-band">{item.risk_band}</span>
                  <strong className="decision-probability">
                    {formatPercent(item.default_probability, 2)}
                  </strong>
                  <span className={`decision-label ${item.decision ?? "unknown"}`}>
                    {item.decision === "approve"
                      ? "Одобрить"
                      : item.decision === "decline"
                        ? "Отказать"
                        : "Архив"}
                  </span>
                </div>
              ))
            ) : (
              <div className="empty-state compact">
                <ScanLine size={25} aria-hidden="true" />
                <strong>Решений пока нет</strong>
                <span>Первая оценка появится здесь автоматически.</span>
              </div>
            )}
          </div>
        </article>

        <article className="panel model-panel">
          <div className="model-panel-head">
            <span className="section-kicker">Production bundle</span>
            <span className={`status-badge ${data?.model.acceptance_status === "passed" ? "success" : ""}`}>
              acceptance {data?.model.acceptance_status ?? "—"}
            </span>
          </div>
          <h3>Модель работает по фиксированному контракту</h3>
          <p>
            Скоринг и worker используют один immutable bundle. Порог решения,
            калибровка и reason codes не расходятся между online и batch.
          </p>
          <dl className="model-facts">
            <div>
              <dt>ROC-AUC</dt>
              <dd>
                {data?.model.metrics.roc_auc != null
                  ? Number(data.model.metrics.roc_auc).toFixed(4)
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>Порог</dt>
              <dd>{formatPercent(data?.model.decision_threshold ?? null, 0)}</dd>
            </div>
            <div>
              <dt>Версия</dt>
              <dd className="mono">{data?.model.model_version.split("-").at(-1) ?? "—"}</dd>
            </div>
          </dl>
          <p className="local-metric-note">
            Метрики относятся к локально сгенерированному bundle и не являются гарантией
            для произвольных данных.
          </p>
          <Link className="button button-soft" href="/model">
            Контракт модели <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </article>
      </section>
    </div>
  );
}
