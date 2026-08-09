import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Calculator, CheckCircle2, ShieldCheck, WalletCards } from "lucide-react";
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
          <div className="public-hero-copy">
            <span className="section-kicker">Платёж · нагрузка · сравнение</span>
            <h1>Рассчитайте платёж и сравните подходящие кредитные предложения</h1>
            <p>
              Укажите примерные данные — Riskline рассчитает платёж, долговую нагрузку
              и покажет предложения партнёров. Паспорт, телефон и документы на первом
              шаге не нужны.
            </p>
            <div className="button-row">
              <Link className="button button-dark" href="/score">
                <Calculator size={18} aria-hidden="true" /> Рассчитать и подобрать
              </Link>
              <Link className="button button-hero-secondary" href="/offers">
                Сравнить предложения <ArrowRight size={17} aria-hidden="true" />
              </Link>
            </div>
            <div className="hero-trust-row" aria-label="Преимущества первого шага">
              {["Без паспорта", "Без телефона", "Без документов"].map((item) => (
                <span key={item}><CheckCircle2 size={15} aria-hidden="true" />{item}</span>
              ))}
            </div>
            <small>Расчёт предварительный. Финальное решение принимает банк.</small>
          </div>
          <div className="hero-calculation-preview" aria-label="Пример результата расчёта">
            <div className="preview-topline"><span>Пример расчёта</span><ShieldCheck size={20} aria-hidden="true" /></div>
            <p>Ориентировочный платёж</p>
            <strong>22 900 ₽ <small>/ месяц</small></strong>
            <div className="preview-facts">
              <div><span>Сумма</span><b>450 000 ₽</b></div>
              <div><span>Срок</span><b>24 месяца</b></div>
              <div><span>Нагрузка</span><b>Комфортная</b></div>
            </div>
            <div className="preview-offer-line"><WalletCards size={19} aria-hidden="true" /><span>После расчёта сравните подходящие варианты</span></div>
          </div>
        </section>

        <section className="public-section" id="how-it-works" aria-labelledby="how-title">
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

        <section className="product-value-section" aria-labelledby="value-title">
          <div>
            <span className="section-kicker">Сравнивайте спокойно</span>
            <h3 id="value-title">Сначала поймите платёж — потом выбирайте предложение</h3>
            <p>Riskline показывает не только список вариантов, но и объясняет, почему предложение подходит по сумме, сроку и выбранной цели.</p>
          </div>
          <ul>
            <li><CheckCircle2 size={18} aria-hidden="true" /><span><strong>Понятный ориентир</strong>Платёж, переплата и остаток бюджета на одном экране.</span></li>
            <li><CheckCircle2 size={18} aria-hidden="true" /><span><strong>Совместимые варианты</strong>Сначала проверяем ограничения, затем сравниваем подходящие предложения.</span></li>
            <li><CheckCircle2 size={18} aria-hidden="true" /><span><strong>Прозрачный переход</strong>Перед сайтом партнёра вы увидите понятное уведомление.</span></li>
          </ul>
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

        <section className="public-final-cta">
          <div><span className="section-kicker">Начните с расчёта</span><h3>Узнайте ориентировочный платёж и перейдите к сравнению</h3><p>Это займёт около двух минут и не потребует контактных данных.</p></div>
          <Link className="button button-dark" href="/score">Рассчитать и подобрать <ArrowRight size={18} aria-hidden="true" /></Link>
        </section>
      </div>
    </AppShell>
  );
}
