import type { Metadata } from "next";
import { SeoGuidePage } from "../components/SeoGuidePage";
export const metadata: Metadata = { title: "Как оценить долговую нагрузку", description: "Простой разбор PTI: отношение примерных ежемесячных кредитных платежей к доходу." };
export default function Page() { return <SeoGuidePage kicker="Долговая нагрузка" title="Как оценить долговую нагрузку" lead="PTI — это отношение текущих и новых примерных кредитных платежей к месячному доходу." points={["Учитывайте действующие кредитные платежи.", "Высокий PTI может снизить комфорт бюджета и шансы одобрения.", "Расчёт не заменяет банковский underwriting."]} />; }
