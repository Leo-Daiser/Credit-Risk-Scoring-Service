import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { HistoryWorkspace } from "../components/HistoryWorkspace";

export const metadata: Metadata = {
  title: "История решений",
  description: "Аудит одиночных решений кредитного скоринга.",
};

export default function HistoryPage() {
  return (
    <AppShell active="history" eyebrow="Audit trail" title="История решений">
      <HistoryWorkspace />
    </AppShell>
  );
}
