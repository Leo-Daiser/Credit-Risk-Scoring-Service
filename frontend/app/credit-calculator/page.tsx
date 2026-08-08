import type { Metadata } from "next";
import { SeoGuidePage } from "../components/SeoGuidePage";
export const metadata: Metadata = { title: "Калькулятор кредита по сумме и сроку", description: "Как предварительно оценить аннуитетный платёж, переплату и долговую нагрузку." };
export default function Page() { return <SeoGuidePage kicker="Кредитный калькулятор" title="Калькулятор кредита по сумме и сроку" lead="Аннуитетный расчёт помогает заранее сопоставить примерный ежемесячный платёж с бюджетом." points={["Введите сумму, срок и примерную ставку.", "Сравните платёж, переплату и PTI.", "Проверьте альтернативный срок или меньшую сумму."]} />; }
