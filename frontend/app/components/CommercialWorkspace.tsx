"use client";

import { AlertTriangle, BarChart3, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import {
  apiFetch,
  type CommercialAnalytics,
  type EventDebugReport,
  formatDate,
  formatPercent,
  type OfferQualityReport,
  type SegmentOpportunityReport,
} from "../lib/api";

interface CommercialData {
  analytics: CommercialAnalytics;
  quality: OfferQualityReport;
  segments: SegmentOpportunityReport;
  debug: EventDebugReport;
}

function formatMoney(value: number): string {
  return `${Math.round(value).toLocaleString("ru-RU")} ₽`;
}

async function fetchCommercialData(): Promise<CommercialData> {
  const [analytics, quality, segments, debug] = await Promise.all([
    apiFetch<CommercialAnalytics>("v1/analytics/commercial-summary?days=30"),
    apiFetch<OfferQualityReport>("v1/offers/quality-report?days=30"),
    apiFetch<SegmentOpportunityReport>("v1/analytics/segment-opportunities?days=30"),
    apiFetch<EventDebugReport>("v1/analytics/event-debug?limit=30"),
  ]);
  return { analytics, quality, segments, debug };
}

export function CommercialWorkspace() {
  const [data, setData] = useState<CommercialData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchCommercialData()
      .then(setData)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    let active = true;
    fetchCommercialData()
      .then((payload) => {
        if (active) setData(payload);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const summary = data?.analytics.summary;
  return (
    <div className="commercial-stack">
      <section className="commercial-hero">
        <div>
          <span className="section-kicker"><BarChart3 size={15} /> Бизнес-показатели</span>
          <h2>Аналитика партнёрских переходов</h2>
          <p>
            Воронка от подбора до партнёрского события, качество предложений и сегменты,
            для которых не хватает подходящих вариантов. Исходные анкеты не отображаются.
          </p>
        </div>
        <div className="operator-boundary"><ShieldCheck size={18} /> Внутренний доступ</div>
      </section>

      {loading ? <div className="commercial-state"><LoaderCircle className="spin" /> Загружаем агрегаты…</div> : null}
      {error ? <div className="connection-banner" role="alert"><AlertTriangle size={18} /><div><strong>Коммерческая аналитика недоступна.</strong><span>{error}</span></div><button className="button button-mini" type="button" onClick={load}><RefreshCw size={15} /> Повторить</button></div> : null}

      <section className="commercial-metrics" aria-label="Аналитика партнёрских переходов">
        <Metric label="Заявки" value={summary?.total_profile_scores ?? 0} />
        <Metric label="Подборы" value={summary?.total_match_requests ?? 0} />
        <Metric label="Показы" value={summary?.total_offer_impressions ?? 0} />
        <Metric label="Переходы" value={summary?.total_offer_clicks ?? 0} />
        <Metric label="CTR" value={formatPercent(summary?.ctr_overall ?? 0)} />
        <Metric label="Без офферов" value={formatPercent(summary?.no_eligible_offers_rate ?? 0)} />
        <Metric label="Выдано" value={formatPercent(summary?.issued_rate ?? 0)} />
        <Metric label="Зафиксированная выручка" value={formatMoney(summary?.estimated_revenue ?? 0)} />
        <Metric label="Доход на переход" value={formatMoney(summary?.epc_proxy ?? 0)} />
        <Metric label="CTR рекомендации" value={formatPercent(summary?.recommended_offer_ctr ?? 0)} />
        <Metric label="Старт оценки" value={formatPercent(summary?.assessment_start_rate ?? 0)} />
        <Metric label="Завершение оценки" value={formatPercent(summary?.assessment_completion_rate ?? 0)} />
        <Metric label="Использование сценариев" value={formatPercent(summary?.scenario_usage_rate ?? 0)} />
        <Metric label="Ошибки перехода" value={summary?.partner_redirect_failures ?? 0} />
      </section>

      <section className="commercial-grid">
        <ReportPanel title="Качество предложений" kicker="Контроль каталога">
          {data?.quality.offers.length ? <div className="commercial-table">{data.quality.offers.map((offer) => <div className="commercial-row" key={offer.offer_id}><div><strong>{offer.product_name}</strong><small>{offer.bank_id} · {offer.status}</small></div><span>{formatPercent(offer.ctr)}</span><div className="quality-flags">{offer.quality_flags.length ? offer.quality_flags.map((flag) => <i key={flag}>{flag}</i>) : <i className="ok">без флагов</i>}</div><b>{offer.recommendation}</b></div>)}</div> : <Empty text="Предложения ещё не загружены." />}
        </ReportPanel>

        <ReportPanel title="Где не хватает предложений" kicker="Потерянный спрос">
          {data?.segments.opportunities.length ? <div className="commercial-table">{data.segments.opportunities.slice(0, 10).map((segment) => <div className="commercial-row segment" key={`${segment.segment_key}-${segment.segment_value}`}><div><strong>{segment.segment_key}: {segment.segment_value}</strong><small>{segment.requests} запросов · lost clicks {segment.estimated_lost_clicks}</small></div><span>{formatPercent(segment.eligible_offer_rate)}</span><b>{segment.recommendation}</b></div>)}</div> : <Empty text="Сегментные возможности появятся после первых подборов." />}
        </ReportPanel>
      </section>

      <section className="commercial-grid">
        <ReportPanel title="Варианты порядка предложений" kicker="Эксперименты">
          {data?.analytics.experiment_metrics.length ? <div className="commercial-table">{data.analytics.experiment_metrics.map((variant) => <div className="commercial-row segment" key={variant.variant}><div><strong>{variant.variant}</strong><small>{variant.impressions} показов · {variant.clicks} кликов</small></div><span>{formatPercent(variant.ctr)}</span><b>{variant.issued} issued</b></div>)}</div> : <Empty text="Эксперименты выключены: весь трафик использует rules_v1." />}
        </ReportPanel>

        <ReportPanel title="Журнал партнёрских событий" kicker="Журнал событий">
          {data?.debug.events.length ? <div className="commercial-table">{data.debug.events.map((event, index) => <div className="commercial-row event" key={`${event.event_type}-${event.click_id}-${index}`}><div><strong>{event.event_type}</strong><small>{event.click_id ?? "без click id"} · {formatDate(event.occurred_at)}</small></div><span>{event.status ?? event.hmac_validation_status ?? "—"}</span><b>{event.experiment_variant}</b></div>)}</div> : <Empty text="Событий пока нет. Raw payload намеренно не отображается." />}
        </ReportPanel>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}

function ReportPanel({ title, kicker, children }: { title: string; kicker: string; children: ReactNode }) {
  return <article className="panel commercial-panel"><div className="panel-heading"><div><span className="section-kicker">{kicker}</span><h3>{title}</h3></div></div>{children}</article>;
}

function Empty({ text }: { text: string }) {
  return <div className="empty-state compact"><strong>Пока пусто</strong><span>{text}</span></div>;
}
