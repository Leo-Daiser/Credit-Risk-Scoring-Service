import type { Metadata } from "next";
import { AppShell } from "../../components/AppShell";
import { ScoreWorkspace } from "../../components/ScoreWorkspace";
import { requireOperatorUi } from "../../lib/access";

export const metadata: Metadata = { title: "Расчётный модуль" };

export default function OperatorScorePage() {
  requireOperatorUi();
  return <AppShell operator active="score" eyebrow="Внутренние операции" title="Расчётный модуль"><ScoreWorkspace /></AppShell>;
}
