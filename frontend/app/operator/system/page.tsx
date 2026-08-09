import type { Metadata } from "next";
import { AppShell } from "../../components/AppShell";
import { ModelWorkspace } from "../../components/ModelWorkspace";
import { requireOperatorUi } from "../../lib/access";

export const metadata: Metadata = {
  title: "Состояние системы",
  description: "Внутреннее состояние расчётного модуля и операционного контура.",
};

export default function OperatorSystemPage() {
  requireOperatorUi();
  return (
    <AppShell operator active="model" eyebrow="Внутренние операции" title="Состояние системы">
      <ModelWorkspace />
    </AppShell>
  );
}
