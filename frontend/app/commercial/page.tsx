import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { CommercialWorkspace } from "../components/CommercialWorkspace";
import { requireOperatorUi } from "../lib/access";

export const metadata: Metadata = {
  title: "Аналитика партнёрских переходов",
  description: "Воронка подбора, качество предложений и сегментные возможности.",
};

export default function CommercialPage() {
  requireOperatorUi();
  return (
    <AppShell
      operator
      active="commercial"
      eyebrow="Кабинет оператора"
      title="Аналитика партнёрских переходов"
    >
      <CommercialWorkspace />
    </AppShell>
  );
}
