import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { ModelWorkspace } from "../components/ModelWorkspace";
import { requireOperatorUi } from "../lib/access";

export const metadata: Metadata = {
  title: "Модель и контур",
  description: "Версия production bundle, input contract и границы архитектуры.",
};

export default function ModelPage() {
  requireOperatorUi();
  return (
    <AppShell operator active="model" eyebrow="Governance" title="Модель и контур">
      <ModelWorkspace />
    </AppShell>
  );
}
