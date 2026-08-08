import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { ScoreWorkspace } from "../components/ScoreWorkspace";

export const metadata: Metadata = {
  title: "Кредитный калькулятор",
  description: "Расчёт кредитной нагрузки и предварительная ML-оценка риска.",
};

export default function ScorePage() {
  return (
    <AppShell active="score" eyebrow="Personal calculator · ML scoring" title="Кредитный калькулятор">
      <ScoreWorkspace />
    </AppShell>
  );
}
