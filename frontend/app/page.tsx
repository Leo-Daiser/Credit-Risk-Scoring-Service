import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Calculator, CheckCircle2, ShieldCheck } from "lucide-react";
import { AppShell } from "./components/AppShell";
import { PublicEventTracker } from "./components/PublicEventTracker";

export const metadata: Metadata = {
  title: "Рассчитать платёж и подобрать кредитные предложения",
  description:
    "Оцените платёж и долговую нагрузку, затем сравните подходящие предложения партнёров без паспорта, телефона и документов на первом шаге.",
};

export default function Home() {
  const demoMode = process.env.DEMO_MODE !== "false";
  return (
    <AppShell active="overview" eyebrow="Кредитный подбор" title="Riskline">
      <PublicEventTracker />
      <div className="public-landing">
        {demoMode ? (
          <div className="connection-banner" role="status">
            <div>
              <strong>Демо-режим</strong>
              <span>Показанные предложения являются тестовыми и недоступны для реальной заявки.</span>
            </div>
          </div>
        ) : null}

        <section className="public-hero saas-hero">
          <span className="section-kicker">Платёж · нагрузка · сравнение</span>
          <h2>Рассчитайте платёж и сравните подходящие кредитные предложения за 2 минуты.</h2>
          <p>
            Укажите примерные данные — сервис покажет ориентировочный платёж, долговую
            нагрузку и предложения партнёров. Паспорт, телефон и документы не нужны для
            предварительного подбора. Финальное решение принимает банк.
          </p>
          <div className="button-row">
            <Link className="button button-dark" href="/score">
              <Calculator size={18} aria-hidden="true" /> Рассчитать и подобрать
            </Link>
            <Link className="button button-soft" href="/offers">
              Сравнить предложения <ArrowRight size={17} aria-hidden="true" />
            </Link>
          </div>
          <small>Расчёт предварительный. Индивидуальные условия определяет партнёр.</small>
        </section>

        <section className="public-section" aria-labelledby="how-title">
          <div className="public-section-heading">
            <span className="section-kicker">Как это работает</span>
            <h3 id="how-title">От расчёта до сравнения — три шага</h3>
          </div>
          <div className="public-card-grid three conversion-steps">
            <article><b>01</b><h4>Рассчитайте платёж</h4><p>Сравните платёж, переплату и остаток бюджета.</p></article>
            <article><b>02</b><h4>Укажите примерные параметры</h4><p>Выберите диапазоны без документов и контактных данных.</p></article>
            <article><b>03</b><h4>Получите предложения</h4><p>Сервис покажет совместимые варианты и объяснит порядок.</p></article>
          </div>
        </section>

        <section className="public-split trust-conversion-block">
          <article className="public-feature privacy-feature">
            <ShieldCheck size={28} aria-hidden="true" />
            <span className="section-kicker">Спокойный первый шаг</span>
            <h3>Без лишних данных</h3>
            <ul className="check-list">
              {["Без паспорта", "Без СНИЛС и ИНН", "Без документов", "Без названия работодателя", "Без данных БКИ", "Без телефона"].map((item) => (
                <li key={item}><CheckCircle2 size={16} aria-hidden="true" />{item}</li>
              ))}
            </ul>
          </article>
          <article className="public-feature comparison-feature">
            <Calculator size={28} aria-hidden="true" />
            <span className="section-kicker">Понятный результат</span>
            <h3>Что покажет сервис</h3>
            <ul className="check-list">
              {["Ориентировочный платёж", "Долговую нагрузку", "Комфорт платежа", "Подходящие предложения", "Причины рекомендации"].map((item) => (
                <li key={item}><CheckCircle2 size={16} aria-hidden="true" />{item}</li>
              ))}
            </ul>
          </article>
        </section>

        <section className="public-disclaimer" aria-label="Условия сервиса">
          <strong>Прозрачно о подборе</strong>
          <p>
            Сервис не принимает кредитных решений. Финальное решение принимает банк.
            Некоторые предложения являются рекламными, и сервис может получить
            вознаграждение за переход. Условия определяет партнёр.
          </p>
        </section>
      </div>
    </AppShell>
  );
}
