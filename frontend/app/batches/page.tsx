import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { BatchWorkspace } from "../components/BatchWorkspace";

export const metadata: Metadata = {
  title: "Пакетный скоринг",
  description: "Безопасная загрузка подготовленных CSV и parquet реестров.",
};

export default function BatchesPage() {
  return (
    <AppShell active="batches" eyebrow="Массовая обработка" title="Пакетный скоринг">
      <BatchWorkspace />
    </AppShell>
  );
}
