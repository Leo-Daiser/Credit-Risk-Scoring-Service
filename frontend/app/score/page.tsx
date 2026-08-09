import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { CalculatorWorkspace } from "../components/CalculatorWorkspace";

export const metadata: Metadata = {
  title: "Кредитный калькулятор",
  description: "Ориентировочный платёж, общая стоимость и долговая нагрузка без отправки введённых значений.",
};

export default function ScorePage() {
  return (
    <AppShell active="score" eyebrow="Расчёт платежа" title="Кредитный калькулятор">
      <CalculatorWorkspace />
    </AppShell>
  );
}
