"use client";

import { DragEvent, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  CheckCircle2,
  Clock3,
  FileSpreadsheet,
  FileUp,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { apiFetch, type BatchJob, formatDate, formatPercent } from "../lib/api";

const statusCopy: Record<BatchJob["status"], string> = {
  queued: "В очереди",
  running: "Обрабатывается",
  completed: "Готово",
  failed: "Ошибка",
};

interface BatchList {
  items: BatchJob[];
  total: number;
}

function isSupported(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith(".csv") || name.endsWith(".parquet") || name.endsWith(".pq");
}

export function BatchWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [idColumn, setIdColumn] = useState("SK_ID_CURR");
  const [dragging, setDragging] = useState(false);
  const [jobs, setJobs] = useState<BatchJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadJobs = async () => {
    try {
      const payload = await apiFetch<BatchList>("v1/batch/jobs?limit=25");
      setJobs(payload.items);
      setError(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    apiFetch<BatchList>("v1/batch/jobs?limit=25")
      .then((payload) => {
        if (active) {
          setJobs(payload.items);
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
  }, []);

  useEffect(() => {
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) return;
    const timer = window.setInterval(() => void loadJobs(), 4000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  const selectFile = (candidate?: File) => {
    if (!candidate) return;
    if (!isSupported(candidate)) {
      setError("Поддерживаются только CSV и parquet файлы.");
      return;
    }
    setFile(candidate);
    setError(null);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("id_column", idColumn);
    try {
      await apiFetch<BatchJob>("v1/batch/jobs", { method: "POST", body: form });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      await loadJobs();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="page-intro">
        <div>
          <span className="section-kicker">Model-ready данные</span>
          <h2>Реестр вошёл. Решения вышли.</h2>
          <p>
            API проверит настроенные лимиты размера и строк, сохранит только метаданные
            задания, worker обработает файл отдельным процессом, а результат вернётся без
            исходных признаков.
          </p>
        </div>
        <a className="button button-ghost" href="/api/backend/v1/batch/template.csv">
          <ArrowDownToLine size={18} aria-hidden="true" />
          Скачать шаблон
        </a>
      </section>

      <section className="batch-layout">
        <article className="upload-card">
          <div className="step-label"><span>01</span> Подготовьте реестр</div>
          <div
            className={`drop-zone ${dragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.parquet,.pq"
              onChange={(event) => selectFile(event.target.files?.[0])}
              hidden
            />
            {file ? (
              <>
                <div className="file-symbol"><FileSpreadsheet size={30} aria-hidden="true" /></div>
                <strong>{file.name}</strong>
                <span>{(file.size / 1024 / 1024).toFixed(2)} МБ · готов к отправке</span>
                <button
                  className="remove-file"
                  type="button"
                  onClick={(event) => { event.stopPropagation(); setFile(null); }}
                >
                  <Trash2 size={16} aria-hidden="true" /> Убрать
                </button>
              </>
            ) : (
              <>
                <div className="upload-symbol"><FileUp size={31} aria-hidden="true" /></div>
                <strong>Перетащите CSV или parquet</strong>
                <span>или нажмите, чтобы выбрать файл · лимит проверит API</span>
              </>
            )}
          </div>

          <label className="field-label" htmlFor="id-column">
            Колонка идентификатора
            <input
              id="id-column"
              value={idColumn}
              onChange={(event) => setIdColumn(event.target.value)}
              spellCheck={false}
            />
            <small>Должна быть уникальной и не входит в признаки модели.</small>
          </label>

          {error ? (
            <div className="form-error" role="alert">
              <ShieldAlert size={18} aria-hidden="true" /> {error}
            </div>
          ) : null}

          <button
            className="button button-dark button-full"
            type="button"
            disabled={!file || uploading}
            onClick={upload}
          >
            {uploading ? <LoaderCircle className="spin" size={18} /> : <FileUp size={18} />}
            {uploading ? "Отправляем…" : "Поставить в очередь"}
          </button>
        </article>

        <aside className="contract-card">
          <div className="step-label inverse"><span>02</span> Контракт загрузки</div>
          <h3>Сервис не переобучает модель на вашем файле</h3>
          <p>
            Он применяет текущий production bundle к таблице с уже подготовленными
            признаками Home Credit. Произвольный банковский экспорт не совместим со схемой.
          </p>
          <ul className="check-list">
            <li><CheckCircle2 size={18} /> Заголовки сверяются с feature schema</li>
            <li><CheckCircle2 size={18} /> Неизвестные признаки отклоняются</li>
            <li><CheckCircle2 size={18} /> Результат содержит ID, PD, решение и риск</li>
            <li><LockKeyhole size={18} /> Исходник удаляется после успешной обработки</li>
          </ul>
          <a className="contract-link" href="/model#contract">Подробнее о формате данных →</a>
        </aside>
      </section>

      <section className="panel jobs-panel">
        <div className="panel-heading">
          <div>
            <span className="section-kicker">Durable queue</span>
            <h3>Последние задания</h3>
          </div>
          <button className="icon-button" type="button" onClick={() => void loadJobs()} aria-label="Обновить очередь">
            <RefreshCw size={18} className={loading ? "spin" : ""} />
          </button>
        </div>

        <div className="jobs-table-wrap">
          <table className="data-table jobs-table">
            <thead>
              <tr>
                <th>Файл</th>
                <th>Создан</th>
                <th>Строк</th>
                <th>Статус</th>
                <th>Результат</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.job_id}>
                  <td>
                    <strong>{job.original_filename}</strong>
                    <small>{job.input_format.toUpperCase()} · {(job.file_size_bytes / 1024).toFixed(0)} КБ</small>
                  </td>
                  <td>{formatDate(job.created_at)}</td>
                  <td>{job.rows_total ?? "—"}</td>
                  <td>
                    <span className={`job-status ${job.status}`}>
                      {job.status === "running" || job.status === "queued" ? (
                        <Clock3 size={14} />
                      ) : job.status === "completed" ? (
                        <CheckCircle2 size={14} />
                      ) : (
                        <ShieldAlert size={14} />
                      )}
                      {statusCopy[job.status]}
                    </span>
                    {job.error_message ? <small className="job-error">{job.error_message}</small> : null}
                  </td>
                  <td>
                    {job.status === "completed" ? (
                      <a className="result-link" href={`/api/backend/v1/batch/jobs/${job.job_id}/result`}>
                        CSV <ArrowDownToLine size={15} />
                      </a>
                    ) : job.status === "running" ? (
                      <span className="progress-copy">
                        {job.rows_total ? formatPercent(job.rows_processed / job.rows_total, 0) : "в работе"}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!jobs.length && !loading ? (
            <div className="empty-state compact">
              <FileSpreadsheet size={26} />
              <strong>Очередь пока пуста</strong>
              <span>Первое задание появится здесь сразу после загрузки.</span>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
