"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Calculator, ShieldCheck } from "lucide-react";
import { calculateCreditScenario } from "../lib/credit-calculator.mjs";
import { parseNumericInput } from "../lib/numeric-input.mjs";
import { createAnonymousSessionId, recordPublicEvent } from "../lib/public-analytics";
import { NumericInput } from "./NumericInput";

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

const affordabilityLabels: Record<string, string> = {
  comfortable: "Комфортная",
  manageable: "Умеренная",
  stretched: "Повышенная",
  high: "Высокая",
  unknown: "Не определена",
};

export function CalculatorWorkspace() {
  const router = useRouter();
  const [sessionId] = useState(createAnonymousSessionId);
  const [amount, setAmount] = useState("450000");
  const [term, setTerm] = useState("24");
  const [rate, setRate] = useState("19.9");
  const [income, setIncome] = useState("120000");
  const [debt, setDebt] = useState("0");
  const parsed = useMemo(() => ({
    amount: parseNumericInput(amount),
    term: parseNumericInput(term),
    rate: parseNumericInput(rate),
    income: parseNumericInput(income),
    debt: parseNumericInput(debt),
  }), [amount, term, rate, income, debt]);
  const error = parsed.amount === null || parsed.amount <= 0
    ? "Укажите сумму больше нуля."
    : parsed.term === null || !Number.isInteger(parsed.term) || parsed.term < 1 || parsed.term > 360
      ? "Укажите целый срок от 1 до 360 месяцев."
      : parsed.rate === null || parsed.rate < 0 || parsed.rate > 100
        ? "Укажите ставку от 0 до 100%."
        : parsed.income === null || parsed.income <= 0
          ? "Укажите месячный доход больше нуля."
          : parsed.debt === null || parsed.debt < 0
            ? "Текущие платежи не могут быть отрицательными."
            : null;
  const result = useMemo(() => {
    if (error) return null;
    return calculateCreditScenario(
      parsed.amount!, parsed.rate!, parsed.term!, parsed.debt!, parsed.income!,
    );
  }, [error, parsed]);

  const continueToMatching = async () => {
    await Promise.allSettled([
      recordPublicEvent("calculator_used", "credit_calculator", sessionId),
      recordPublicEvent("calculator_continue_clicked", "credit_calculator", sessionId),
    ]);
    router.push("/offers");
  };

  return (
    <div className="page-stack">
      <section className="page-intro score-intro">
        <div>
          <span className="section-kicker">Публичный калькулятор</span>
          <h2>Рассчитайте платёж и долговую нагрузку без отправки данных.</h2>
          <p>Все вычисления выполняются в браузере. Значения не отправляются на backend и не сохраняются в browser storage.</p>
        </div>
      </section>
      <section className="score-layout">
        <article className="panel score-form">
          <div className="panel-heading"><h3>Параметры сценария</h3><Calculator size={24} aria-hidden="true" /></div>
          <p className="field-help">Можно указать примерные значения. Расчёт не включает страховки, комиссии и индивидуальные условия банка.</p>
          <div className="personal-fields two-columns">
            <CalculatorField id="public-amount" label="Сумма, ₽" value={amount} onChange={setAmount} min="1" />
            <CalculatorField id="public-term" label="Срок, месяцев" value={term} onChange={setTerm} min="1" max="360" step="1" />
            <CalculatorField id="public-rate" label="Примерная ставка, %" value={rate} onChange={setRate} min="0" max="100" step="0.1" />
            <CalculatorField id="public-income" label="Доход в месяц, ₽" value={income} onChange={setIncome} min="1" />
            <CalculatorField id="public-debt" label="Текущие платежи, ₽" value={debt} onChange={setDebt} min="0" />
          </div>
          {error ? <div className="form-error" role="alert" id="calculator-error"><AlertTriangle size={18} aria-hidden="true" />{error}</div> : null}
        </article>
        <aside className="panel calculator-result" aria-live="polite">
          <div className="panel-heading"><h3>Предварительный результат</h3><ShieldCheck size={24} aria-hidden="true" /></div>
          {result ? (
            <>
              <dl className="calculator-facts">
                <div><dt>Платёж в месяц</dt><dd>{money.format(result.payment)}</dd></div>
                <div><dt>Всего к возврату</dt><dd>{money.format(result.totalRepayment)}</dd></div>
                <div><dt>Переплата</dt><dd>{money.format(result.overpayment)}</dd></div>
                <div><dt>Долговая нагрузка</dt><dd>{result.pti === null ? "—" : `${(result.pti * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Диапазон нагрузки</dt><dd>{affordabilityLabels[result.affordabilityBand]}</dd></div>
              </dl>
              {result.pti !== null && result.pti > 0.5 ? (
                <div className="pti-warning" role="status"><AlertTriangle size={18} aria-hidden="true" />Расчётная нагрузка повышена. Проверьте более длинный срок или меньшую сумму.</div>
              ) : null}
              <button className="button button-dark button-full" type="button" onClick={continueToMatching}>
                Продолжить к privacy-light подбору <ArrowRight size={17} aria-hidden="true" />
              </button>
            </>
          ) : <p className="empty-copy">Исправьте параметры — расчёт появится без отправки данных.</p>}
          <p className="model-disclaimer">Расчёт приблизительный. Фактическая ставка, платёж и решение определяются банком после проверки анкеты.</p>
        </aside>
      </section>
    </div>
  );
}

function CalculatorField({ id, label, value, onChange, ...props }: {
  id: string; label: string; value: string; onChange: (value: string) => void;
  min?: string; max?: string; step?: string;
}) {
  return (
    <label className="field-label" htmlFor={id}>
      {label}
      <NumericInput id={id} value={value} onValueChange={onChange} aria-describedby="calculator-error" {...props} />
    </label>
  );
}
