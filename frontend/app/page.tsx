import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CircleGauge,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  WalletCards,
} from "lucide-react";
import { AppShell } from "./components/AppShell";
import { PublicEventTracker } from "./components/PublicEventTracker";

export const metadata: Metadata = {
  title: "Оценка финансового профиля и подбор предложений",
  description:
    "Получите оценку Riskline, объяснение факторов, сценарии улучшения и подходящие кредитные предложения без паспорта и телефона.",
};

const trustItems = [
  "Без паспорта",
  "Без телефона",
  "Без загрузки документов",
  "Около 2 минут",
];

export default function Home() {
  const demoMode = process.env.DEMO_MODE !== "false";
  return (
    <AppShell active="overview" eyebrow="Финансовая оценка" title="Riskline">
      <PublicEventTracker />
      <div className="public-landing assessment-landing">
        {demoMode ? (
          <div className="connection-banner" role="status">
            <div>
              <strong>Демо-режим</strong>
              <span>Предложения синтетические и недоступны для реальной заявки.</span>
            </div>
          </div>
        ) : null}

        <section className="public-hero assessment-hero">
          <div className="public-hero-copy">
            <span className="section-kicker">Профиль · факторы · сценарии · предложения</span>
            <h1>Узнайте, какие кредитные предложения подходят вашему финансовому профилю</h1>
            <p>
              Ответьте на несколько вопросов — Riskline оценит финансовый профиль,
              покажет, что влияет на результат, предложит способы улучшить сценарий
              и подберёт подходящие предложения.
            </p>
            <div className="button-row">
              <Link className="button button-dark" href="/assessment">
                Оценить профиль <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link className="button button-hero-secondary" href="/score">
                Рассчитать кредит
              </Link>
            </div>
            <div className="hero-trust-row" aria-label="Условия оценки">
              {trustItems.map((item) => (
                <span key={item}><CheckCircle2 size={15} aria-hidden="true" />{item}</span>
              ))}
            </div>
            <small>Оценка предварительная. Финальное решение принимает банк.</small>
          </div>
          <ExampleResult />
        </section>

        <section className="public-section" id="how-it-works" aria-labelledby="how-title">
          <div className="public-section-heading">
            <span className="section-kicker">Как работает Riskline</span>
            <h2 id="how-title">От короткого профиля к понятным вариантам</h2>
          </div>
          <div className="public-card-grid three assessment-steps-preview">
            <article><b>01</b><h3>Расскажите о ситуации</h3><p>Укажите сумму, срок, доход, занятость и текущие платежи.</p></article>
            <article><b>02</b><h3>Получите оценку Riskline</h3><p>Сервис сравнит профиль, долговую нагрузку и комфорт нового платежа.</p></article>
            <article><b>03</b><h3>Проверьте варианты</h3><p>Посмотрите факторы, сценарии улучшения и расчёт для каждого предложения.</p></article>
          </div>
        </section>

        <section className="landing-result-story" aria-labelledby="learn-title">
          <div>
            <span className="section-kicker">Что вы узнаете</span>
            <h2 id="learn-title">Не только платёж, а целостную картину</h2>
            <p>Riskline разделяет финансовый расчёт, оценку профиля и совместимость с продуктами — поэтому результат остаётся понятным.</p>
          </div>
          <div className="landing-value-list">
            <article><CircleGauge size={23} /><strong>Профиль Riskline</strong><span>Внутренний ориентир сервиса без обещаний банковского решения.</span></article>
            <article><Sparkles size={23} /><strong>Что влияет на результат</strong><span>Понятные сильные стороны и факторы, которые ограничивают сценарий.</span></article>
            <article><WalletCards size={23} /><strong>Подходящие предложения</strong><span>Индивидуальный диапазон платежа по условиям каждого продукта.</span></article>
          </div>
        </section>

        <section className="improvement-story" aria-labelledby="improve-title">
          <div className="improvement-story-copy">
            <span className="section-kicker">Как можно улучшить сценарий</span>
            <h2 id="improve-title">Проверьте изменения до обращения к партнёру</h2>
            <p>Сервис пересчитывает управляемые параметры и показывает направление изменений без советов искажать доход, занятость или обязательства.</p>
            <Link className="inline-link" href="/assessment">Получить свои сценарии <ArrowRight size={16} /></Link>
          </div>
          <div className="landing-scenario-card">
            <SlidersHorizontal size={24} aria-hidden="true" />
            <div><span>Сумма</span><strong>800 000 ₽ → 650 000 ₽</strong></div>
            <div><span>Ориентировочный платёж</span><strong>31 400 ₽ → 25 500 ₽</strong></div>
            <div><span>Долговая нагрузка</span><strong>38% → 31%</strong></div>
            <small>Пример интерфейса. Конкретный результат зависит от введённых данных.</small>
          </div>
        </section>

        <section className="product-value-section" aria-labelledby="matching-title">
          <div>
            <span className="section-kicker">Персональный подбор</span>
            <h2 id="matching-title">Почему предложения показаны именно в таком порядке</h2>
            <p>Сначала проверяются обязательные ограничения продукта, затем комфорт платежа, профиль Riskline, цель и совместимость параметров.</p>
          </div>
          <ul>
            <li><CheckCircle2 size={18} /><span><strong>Плохая совместимость не маскируется</strong>Вознаграждение партнёра используется только как вторичный критерий.</span></li>
            <li><CheckCircle2 size={18} /><span><strong>Каждый продукт рассчитан отдельно</strong>Диапазон платежа учитывает его сумму, срок и ставку.</span></li>
            <li><CheckCircle2 size={18} /><span><strong>Переход прозрачен</strong>Перед сайтом партнёра сервис показывает отдельное уведомление.</span></li>
          </ul>
        </section>

        <section className="public-split trust-conversion-block">
          <article className="public-feature privacy-feature">
            <ShieldCheck size={28} aria-hidden="true" />
            <span className="section-kicker">Privacy-light</span>
            <h2>Без лишних данных</h2>
            <ul className="check-list">
              {["Без паспорта", "Без СНИЛС и ИНН", "Без документов", "Без названия работодателя", "Без данных БКИ", "Без телефона"].map((item) => (
                <li key={item}><CheckCircle2 size={16} />{item}</li>
              ))}
            </ul>
          </article>
          <article className="public-feature comparison-feature">
            <CircleGauge size={28} aria-hidden="true" />
            <span className="section-kicker">Границы оценки</span>
            <h2>Riskline помогает сравнить, но не решает за банк</h2>
            <p>Сервис использует собственную модель и общие финансовые параметры. Он не является БКИ, официальным кредитным рейтингом и не предсказывает решение банка.</p>
          </article>
        </section>

        <section className="public-final-cta assessment-final-cta">
          <div><span className="section-kicker">Начните с оценки</span><h2>Получите персональный результат примерно за 2 минуты</h2><p>Можно указывать приблизительные значения. Контактные данные не нужны.</p></div>
          <Link className="button button-dark" href="/assessment">Оценить профиль <ArrowRight size={18} /></Link>
        </section>

        <section className="public-disclaimer" aria-label="Условия сервиса">
          <strong>Предварительная оценка и рекламные предложения</strong>
          <p>Riskline не принимает кредитных решений. Финальные критерии, условия и решение определяет банк. Некоторые предложения являются рекламными, и сервис может получить вознаграждение за переход.</p>
        </section>
      </div>
    </AppShell>
  );
}

function ExampleResult() {
  return (
    <article className="landing-profile-preview" aria-label="Пример интерфейса результата">
      <div className="preview-topline"><span>Пример интерфейса</span><ShieldCheck size={20} /></div>
      <div className="landing-index-row"><strong>74</strong><span>/ 100<small>Riskline Index</small></span></div>
      <div className="landing-index-track"><i style={{ width: "74%" }} /></div>
      <h2>Устойчивый профиль</h2>
      <div className="preview-facts">
        <div><span>Нагрузка</span><b>31%</b></div>
        <div><span>Предложения</span><b>4</b></div>
      </div>
      <div className="preview-insight"><CheckCircle2 size={17} /><span>Умеренная текущая нагрузка и хороший запас дохода</span></div>
      <div className="preview-insight is-improvement"><Sparkles size={17} /><span>Уменьшение суммы может сделать сценарий устойчивее</span></div>
      <small>Это статический пример, а не результат реального пользователя.</small>
    </article>
  );
}
