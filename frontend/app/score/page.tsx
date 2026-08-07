import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { ScoreWorkspace } from "../components/ScoreWorkspace";

export const metadata: Metadata = {
  title: "Новая оценка",
  description: "Одиночный скоринг по versioned feature-контракту.",
};

export default function ScorePage() {
  return (
    <AppShell active="score" eyebrow="Online inference" title="Новая оценка">
      <ScoreWorkspace />
    </AppShell>
  );
}
