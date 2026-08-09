import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { BatchWorkspace } from "../components/BatchWorkspace";
import { requireOperatorUi } from "../lib/access";

export const metadata: Metadata = {
  title: "Импорт и задачи",
  description: "Безопасная загрузка подготовленных CSV и parquet реестров.",
};

export default function BatchesPage() {
  requireOperatorUi();
  return (
    <AppShell operator active="batches" eyebrow="Внутренние операции" title="Импорт и задачи">
      <BatchWorkspace />
    </AppShell>
  );
}
