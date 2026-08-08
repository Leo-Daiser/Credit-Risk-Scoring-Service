"use client";

import { useMemo, useState } from "react";
import { Calculator, ShieldCheck } from "lucide-react";
import { calculateAnnuity } from "../lib/credit-calculator.mjs";
import { NumericInput } from "./NumericInput";

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

export function CalculatorWorkspace() {
  const [amount, setAmount] = useState("450000");
  const [term, setTerm] = useState("24");
  const [rate, setRate] = useState("19.9");
  const [income, setIncome] = useState("120000");
  const [debt, setDebt] = useState("0");
  const result = useMemo(() => {
    const payment = calculateAnnuity(Number(amount), Number(rate), Number(term));
    const totalDebt = payment + Number(debt || 0);
    const pti = Number(income) > 0 ? totalDebt / Number(income) : 0;
    return { payment, totalDebt, pti };
  }, [amount, term, rate, income, debt]);

  return (
    <div className="page-stack">
      <section className="page-intro score-intro">
        <div>
          <span className="section-kicker">Публичный калькулятор</span>
          <h2>Рассчитайте платёж и долговую нагрузку без отправки данных.</h2>
          <p>Расчёт выполняется в браузере и не является решением банка или финансовой рекомендацией.</p>
        </div>
      </section>
      <section className="score-layout">
        <article className="panel score-form">
          <div className="panel-heading"><h3>Параметры сценария</h3><Calculator size={24} /></div>
          <div className="personal-fields two-columns">
            <label className="field-label" htmlFor="public-amount">Сумма, ₽<NumericInput id="public-amount" value={amount} onValueChange={setAmount} min="10000" /></label>
            <label className="field-label" htmlFor="public-term">Срок, месяцев<NumericInput id="public-term" value={term} onValueChange={setTerm} min="1" max="360" /></label>
            <label className="field-label" htmlFor="public-rate">Ставка, %<NumericInput id="public-rate" value={rate} onValueChange={setRate} min="0" max="100" /></label>
            <label className="field-label" htmlFor="public-income">Доход в месяц, ₽<NumericInput id="public-income" value={income} onValueChange={setIncome} min="1" /></label>
            <label className="field-label" htmlFor="public-debt">Текущие платежи, ₽<NumericInput id="public-debt" value={debt} onValueChange={setDebt} min="0" /></label>
          </div>
        </article>
        <aside className="panel">
          <div className="panel-heading"><h3>Предварительный результат</h3><ShieldCheck size={24} /></div>
          <dl className="model-facts">
            <div><dt>Новый платёж</dt><dd>{money.format(result.payment)}</dd></div>
            <div><dt>Все платежи</dt><dd>{money.format(result.totalDebt)}</dd></div>
            <div><dt>Долговая нагрузка</dt><dd>{(result.pti * 100).toFixed(1)}%</dd></div>
          </dl>
          <p className="model-disclaimer">Фактическая ставка, платёж и решение определяются банком после проверки анкеты.</p>
        </aside>
      </section>
    </div>
  );
}
