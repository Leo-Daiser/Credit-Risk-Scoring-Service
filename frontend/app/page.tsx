import type { Metadata } from "next";
import Link from "next/link";
import { BrainCircuit, Calculator, CheckCircle2, ShieldCheck } from "lucide-react";
import { AppShell } from "./components/AppShell";
import { PublicEventTracker } from "./components/PublicEventTracker";

export const metadata: Metadata = {
  title: "Предварительный подбор кредитных предложений",
  description: "Расчёт платежа и долговой нагрузки, privacy-light профиль и предварительный подбор предложений без паспорта и звонков.",
};

export default function Home() {
  const demoMode = process.env.DEMO_MODE !== "false";
  return (
    <AppShell active="overview" eyebrow="Public MVP · privacy-light" title="Предварительный подбор">
      <PublicEventTracker />
      <div className="public-landing">
        {demoMode ? (
          <div className="connection-banner" role="status">
            <div><strong>Демонстрационный режим</strong><span>Офферы и результаты являются тестовыми данными, а не банковскими решениями.</span></div>
          </div>
        ) : null}
        <section className="public-hero">
          <span className="section-kicker">Платёж · нагрузка · предложения</span>
          <h2>Проверьте кредитную нагрузку и подберите подходящие предложения без паспорта и звонков.</h2>
          <p>Получите предварительный кредитный профиль по примерным данным, оцените платёж и сравните совместимые рекламные или реферальные предложения.</p>
          <div className="button-row">
            <Link className="button button-dark" href="/score"><Calculator size={18} aria-hidden="true" />Рассчитать платёж</Link>
            <Link className="button button-soft" href="/offers">Подобрать предложения</Link>
          </div>
          <small>Финальное решение и условия определяет банк после собственной проверки.</small>
        </section>

        <section className="public-section" aria-labelledby="how-title">
          <div className="public-section-heading"><span className="section-kicker">Как это работает</span><h3 id="how-title">Три понятных шага</h3></div>
          <div className="public-card-grid three">
            <article><b>01</b><h4>Введите примерные данные</h4><p>Сумма, срок и диапазоны — без идентифицирующих документов.</p></article>
            <article><b>02</b><h4>Получите предварительный профиль</h4><p>Увидите расчётный платёж, PTI и ограничения полноты данных.</p></article>
            <article><b>03</b><h4>Сравните предложения</h4><p>Hard rules отфильтруют несовместимые варианты, а ranking упорядочит оставшиеся.</p></article>
          </div>
        </section>

        <section className="public-split">
          <article className="public-feature privacy-feature">
            <ShieldCheck size={28} aria-hidden="true" />
            <span className="section-kicker">Privacy-light</span>
            <h3>Что мы не собираем</h3>
            <ul className="check-list">
              {["Паспорт", "СНИЛС и ИНН", "Документы", "Название работодателя", "Данные БКИ", "Телефон"].map((item) => <li key={item}><CheckCircle2 size={16} aria-hidden="true" />{item}</li>)}
            </ul>
          </article>
          <article className="public-feature">
            <BrainCircuit size={28} aria-hidden="true" />
            <span className="section-kicker">Как используется ML</span>
            <h3>Три отдельных расчётных слоя</h3>
            <p>ML-модель помогает оценить предварительный risk profile. PTI/affordability engine оценивает долговую нагрузку. Offer matching ранжирует только совместимые предложения.</p>
            <p>Результат предварительный и зависит от полноты введённых данных.</p>
          </article>
        </section>

        <section className="public-disclaimer" aria-label="Важные условия">
          <strong>Важно до перехода к предложению</strong>
          <p>Сервис не принимает кредитных решений. Финальное решение принимает банк. Некоторые ссылки могут быть рекламными или реферальными, а условия всегда определяются банком.</p>
        </section>
      </div>
    </AppShell>
  );
}
