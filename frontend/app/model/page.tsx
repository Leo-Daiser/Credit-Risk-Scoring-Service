import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { ModelWorkspace } from "../components/ModelWorkspace";

export const metadata: Metadata = {
  title: "Модель и контур",
  description: "Версия production bundle, input contract и границы архитектуры.",
};

export default function ModelPage() {
  return (
    <AppShell active="model" eyebrow="Governance" title="Модель и контур">
      <ModelWorkspace />
    </AppShell>
  );
}
