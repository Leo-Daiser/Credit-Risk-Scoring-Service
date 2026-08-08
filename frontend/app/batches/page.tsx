import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { BatchWorkspace } from "../components/BatchWorkspace";
import { requireOperatorUi } from "../lib/access";

export const metadata: Metadata = {
  title: "Пакетный скоринг",
  description: "Безопасная загрузка подготовленных CSV и parquet реестров.",
};

export default function BatchesPage() {
  requireOperatorUi();
  return (
    <AppShell operator active="batches" eyebrow="Массовая обработка" title="Пакетный скоринг">
      <BatchWorkspace />
    </AppShell>
  );
}
