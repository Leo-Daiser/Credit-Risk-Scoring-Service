import type { Metadata } from "next";
import { AppShell } from "./components/AppShell";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Предварительный подбор кредитных предложений",
  description: "Privacy-light расчёт нагрузки и предварительный подбор рекламных предложений.",
};

export default function Home() {
  const demoMode = process.env.DEMO_MODE !== "false";
  return (
    <AppShell active="overview" eyebrow="Public MVP · privacy-light" title="Предварительный подбор">
      <div className="page-stack">
        {demoMode ? (
          <div className="connection-banner" role="status">
            <div><strong>Демонстрационный режим</strong><span>Офферы, вероятности и доход являются тестовыми данными, а не банковскими решениями.</span></div>
          </div>
        ) : null}
        <section className="page-intro">
          <div>
            <span className="section-kicker">Расчёт · профиль · предложения</span>
            <h2>Оцените нагрузку и найдите подходящие кредитные предложения.</h2>
            <p>
              Сервис использует только указанные вами диапазоны данных. Результат предварительный,
              а финальное решение по заявке всегда принимает банк.
            </p>
          </div>
        </section>
        <section className="metric-grid" aria-label="Как работает сервис">
          <article className="metric-card"><span>1. Калькулятор</span><strong>Платёж и PTI</strong><small>Расчёт выполняется без заявки в банк.</small></article>
          <article className="metric-card"><span>2. Кредитный профиль</span><strong>Только диапазоны</strong><small>Без паспорта, телефона, документов и данных БКИ.</small></article>
          <article className="metric-card"><span>3. Offer matching</span><strong>Предварительный подбор</strong><small>Переходы могут быть рекламными или реферальными.</small></article>
        </section>
        <section className="panel">
          <h3>Начните с безопасного финансового сценария</h3>
          <p>Сравните расчётный платёж с доходом или сразу заполните privacy-light профиль.</p>
          <div className="button-row">
            <Link className="button button-dark" href="/score">Открыть калькулятор</Link>
            <Link className="button button-soft" href="/offers">Подобрать предложения</Link>
          </div>
          <p className="model-disclaimer">Это не гарантия одобрения и не банковское решение. Условия уточняются у рекламодателя.</p>
        </section>
      </div>
    </AppShell>
  );
}
