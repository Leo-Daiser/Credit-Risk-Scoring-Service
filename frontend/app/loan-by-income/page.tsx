import type { Metadata } from "next";
import { SeoGuidePage } from "../components/SeoGuidePage";
export const metadata: Metadata = { title: "Комфортный платёж по доходу", description: "Как сопоставить примерный кредитный платёж с доходом и текущей долговой нагрузкой." };
export default function Page() { return <SeoGuidePage kicker="Кредит по доходу" title="Какой платёж комфортен при вашем доходе" lead="Оценивайте не только сумму кредита, но и общий месячный платёж после добавления текущих обязательств." points={["Оставляйте запас на обязательные расходы.", "Проверяйте несколько сроков.", "Не воспринимайте предварительный диапазон как решение банка."]} />; }
