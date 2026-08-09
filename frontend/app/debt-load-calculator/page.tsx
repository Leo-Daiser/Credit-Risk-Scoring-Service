import type { Metadata } from "next";
import { SeoGuidePage } from "../components/SeoGuidePage";

export const metadata: Metadata = {
  title: "Как оценить долговую нагрузку",
  description: "Отношение примерных ежемесячных кредитных платежей к доходу.",
};

export default function Page() {
  return (
    <SeoGuidePage
      kicker="Долговая нагрузка"
      title="Как оценить долговую нагрузку"
      lead="Сопоставьте текущие и новые примерные кредитные платежи с месячным доходом."
      points={[
        "Учитывайте действующие кредитные платежи.",
        "Высокая нагрузка может снизить комфорт бюджета.",
        "Расчёт не заменяет проверку банка.",
      ]}
    />
  );
}
