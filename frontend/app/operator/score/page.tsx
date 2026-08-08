import type { Metadata } from "next";
import { AppShell } from "../../components/AppShell";
import { ScoreWorkspace } from "../../components/ScoreWorkspace";
import { requireOperatorUi } from "../../lib/access";

export const metadata: Metadata = { title: "Внутренний ML-скоринг" };

export default function OperatorScorePage() {
  requireOperatorUi();
  return <AppShell operator active="score" eyebrow="Operator · raw model" title="ML-скоринг"><ScoreWorkspace /></AppShell>;
}
