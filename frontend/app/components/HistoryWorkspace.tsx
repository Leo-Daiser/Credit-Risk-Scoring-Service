"use client";

import { useEffect, useState } from "react";
import { Check, Clock3, Filter, RefreshCw, ScanSearch, X } from "lucide-react";
import { apiFetch, formatDate, formatPercent, type HistoryItem } from "../lib/api";

interface HistoryResponse {
  items: HistoryItem[];
  total: number;
}

type DecisionFilter = "all" | "approve" | "decline";

export function HistoryWorkspace() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [decision, setDecision] = useState<DecisionFilter>("all");
  const [riskBand, setRiskBand] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: "100" });
    if (decision !== "all") params.set("decision", decision);
    if (riskBand.trim()) params.set("risk_band", riskBand.trim());
    try {
      const payload = await apiFetch<HistoryResponse>(`v1/scoring/history?${params}`);
      setItems(payload.items);
      setTotal(payload.total);
      setError(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ limit: "100" });
    if (decision !== "all") params.set("decision", decision);
    apiFetch<HistoryResponse>(`v1/scoring/history?${params}`)
      .then((payload) => {
        if (active) {
          setItems(payload.items);
          setTotal(payload.total);
          setError(null);
        }
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
  }, [decision]);

  return (
    <div className="page-stack">
      <section className="page-intro">
        <div>
          <span className="section-kicker">Immutable audit</span>
          <h2>Каждое решение можно восстановить.</h2>
          <p>
            Request ID связывает входной payload, версию модели, порог и прогноз в одной
            транзакции. Чувствительные признаки в таблице интерфейса не показываются.
          </p>
        </div>
        <div className="history-total"><strong>{total}</strong><span>записей найдено</span></div>
      </section>

      <section className="panel history-panel">
        <div className="history-toolbar">
          <div className="segmented-control" aria-label="Фильтр по решению">
            <button className={decision === "all" ? "is-active" : ""} onClick={() => setDecision("all")} type="button">Все</button>
            <button className={decision === "approve" ? "is-active" : ""} onClick={() => setDecision("approve")} type="button"><Check size={15} /> Одобрить</button>
            <button className={decision === "decline" ? "is-active" : ""} onClick={() => setDecision("decline")} type="button"><X size={15} /> Отказать</button>
          </div>
          <div className="toolbar-filter">
            <Filter size={17} />
            <input
              value={riskBand}
              onChange={(event) => setRiskBand(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void load(); }}
              placeholder="Риск-группа"
              aria-label="Фильтр по риск-группе"
            />
            <button type="button" onClick={() => void load()} aria-label="Применить фильтр">
              <RefreshCw size={17} className={loading ? "spin" : ""} />
            </button>
          </div>
        </div>

        {error ? <div className="form-error history-error" role="alert">{error}</div> : null}

        <div className="history-table-wrap">
          <table className="data-table history-table">
            <thead>
              <tr><th>Request ID</th><th>Время</th><th>PD</th><th>Риск</th><th>Решение</th><th>Версия</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.request_id}>
                  <td><strong className="mono">{item.request_id}</strong></td>
                  <td><span className="date-cell"><Clock3 size={15} /> {formatDate(item.received_at)}</span></td>
                  <td><strong>{formatPercent(item.default_probability, 2)}</strong></td>
                  <td><span className="risk-band">{item.risk_band}</span></td>
                  <td><span className={`decision-label ${item.decision ?? "unknown"}`}>{item.decision === "approve" ? "Одобрить" : item.decision === "decline" ? "Отказать" : "Архив"}</span></td>
                  <td><span className="mono version-cell">{item.model_version.split("-").at(-1)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && !loading ? (
            <div className="empty-state">
              <ScanSearch size={31} />
              <strong>По фильтрам ничего не найдено</strong>
              <span>Измените условия или создайте новую оценку.</span>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
