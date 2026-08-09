"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Calculator, ShieldCheck } from "lucide-react";
import { calculateCreditScenario } from "../lib/credit-calculator.mjs";
import { setTransientAssessmentContext } from "../lib/assessment-context";
import { parseNumericInput } from "../lib/numeric-input.mjs";
import { createAnonymousSessionId, recordPublicEvent } from "../lib/public-analytics";
import { NumericInput } from "./NumericInput";
import { PUBLIC_PROFILE_LIMITS } from "../lib/public-profile-constraints";

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
  const [amount, setAmount] = useState("");
  const [term, setTerm] = useState("");
  const [rate, setRate] = useState("19.9");
  const [income, setIncome] = useState("");
  const [debt, setDebt] = useState("");
  const parsed = useMemo(() => ({
    amount: parseNumericInput(amount),
    term: parseNumericInput(term),
    rate: parseNumericInput(rate),
    income: parseNumericInput(income),
    debt: parseNumericInput(debt),
  }), [amount, term, rate, income, debt]);
  const error = parsed.amount === null || parsed.amount <= 0
    ? "Укажите сумму больше нуля."
    : parsed.amount > PUBLIC_PROFILE_LIMITS.amountMax
      ? "Максимальная сумма для подбора — 10 000 000 ₽."
    : parsed.term === null || !Number.isInteger(parsed.term) || parsed.term < PUBLIC_PROFILE_LIMITS.termMinMonths || parsed.term > PUBLIC_PROFILE_LIMITS.termMaxMonths
      ? "Укажите целый срок от 3 до 120 месяцев."
      : parsed.rate === null || parsed.rate < 0 || parsed.rate > 100
        ? "Укажите ставку от 0 до 100%."
        : parsed.income === null || parsed.income <= 0 || parsed.income > PUBLIC_PROFILE_LIMITS.monthlyIncomeMax
          ? "Укажите месячный доход больше нуля."
          : parsed.debt === null || parsed.debt < 0 || parsed.debt > PUBLIC_PROFILE_LIMITS.existingPaymentsMax
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
    setTransientAssessmentContext({
      amount: parsed.amount!,
      term: parsed.term!,
      monthlyIncome: parsed.income!,
      existingPayments: parsed.debt!,
    });
    router.push("/assessment");
  };

  return (
    <div className="page-stack">
      <section className="page-intro score-intro">
        <div>
          <span className="section-kicker">Расчёт без регистрации</span>
          <h1>Проверьте, какой платёж подходит вашему бюджету.</h1>
          <p>Все вычисления выполняются на этой странице. Введённые значения никуда не отправляются и не сохраняются.</p>
        </div>
      </section>
      <section className="score-layout">
        <article className="panel score-form">
          <div className="panel-heading"><h3>Параметры сценария</h3><Calculator size={24} aria-hidden="true" /></div>
          <p className="field-help">Можно указать примерные значения. Расчёт не включает страховки, комиссии и индивидуальные условия банка.</p>
          <div className="personal-fields two-columns">
            <CalculatorField id="public-amount" label="Сумма, ₽" value={amount} onChange={setAmount} min="1" />
            <CalculatorField id="public-term" label="Срок, месяцев" value={term} onChange={setTerm} min="3" max="120" step="1" />
            <CalculatorField id="public-rate" label="Примерная ставка, %" value={rate} onChange={setRate} min="0" max="100" step="0.1" />
            <CalculatorField id="public-income" label="Ваш регулярный доход в месяц, ₽" value={income} onChange={setIncome} min="1" />
            <CalculatorField id="public-debt" label="Текущие кредитные платежи, ₽" value={debt} onChange={setDebt} min="0" />
          </div>
          {error ? <div className="form-error" role="alert" id="calculator-error"><AlertTriangle size={18} aria-hidden="true" />{error}</div> : null}
        </article>
        <aside className="panel calculator-result" aria-live="polite">
          <div className="panel-heading"><div><span className="section-kicker">Ваш ориентир</span><h3>Предварительный результат</h3></div><ShieldCheck size={24} aria-hidden="true" /></div>
          {result ? (
            <>
              <div className="calculator-primary-fact">
                <span>Платёж в месяц</span>
                <strong>{money.format(result.payment)}</strong>
                <small>ориентировочно по указанным параметрам</small>
              </div>
              <button className="button button-dark button-full" type="button" onClick={continueToMatching}>
                Оценить профиль и подобрать предложения <ArrowRight size={17} aria-hidden="true" />
              </button>
              <dl className="calculator-facts">
                <div><dt>Всего к возврату</dt><dd>{money.format(result.totalRepayment)}</dd></div>
                <div><dt>Переплата</dt><dd>{money.format(result.overpayment)}</dd></div>
                <div><dt>Долговая нагрузка</dt><dd>{result.pti === null ? "—" : `${(result.pti * 100).toFixed(1)}%`}</dd></div>
                <div><dt>После кредитных платежей</dt><dd>{money.format(result.remainingBudget)}</dd></div>
                <div><dt>Комфорт платежа</dt><dd>{affordabilityLabels[result.affordabilityBand]}</dd></div>
              </dl>
              {result.pti !== null && result.pti > 0.5 ? (
                <div className="pti-warning" role="status"><AlertTriangle size={18} aria-hidden="true" />Расчётная нагрузка повышена. Проверьте более длинный срок или меньшую сумму.</div>
              ) : null}
              <button className="button button-ghost button-full" type="button" onClick={() => document.getElementById("public-amount")?.focus()}>
                Изменить параметры
              </button>
            </>
          ) : <p className="empty-copy">Исправьте параметры — расчёт появится без отправки данных.</p>}
          <p className="model-disclaimer">Расчёт приблизительный. Фактическая ставка, платёж и решение определяются банком после проверки анкеты.</p>
          {result ? <p className="remaining-budget-note">Остаток рассчитан как указанный доход минус текущие и новый кредитные платежи. Аренда, продукты, коммунальные и другие повседневные расходы не учтены.</p> : null}
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
