import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { HistoryWorkspace } from "../components/HistoryWorkspace";
import { requireOperatorUi } from "../lib/access";

export const metadata: Metadata = {
  title: "Заявки и подборы",
  description: "Аудит одиночных решений кредитного скоринга.",
};

export default function HistoryPage() {
  requireOperatorUi();
  return (
    <AppShell operator active="history" eyebrow="Журнал операций" title="Заявки и подборы">
      <HistoryWorkspace />
    </AppShell>
  );
}
