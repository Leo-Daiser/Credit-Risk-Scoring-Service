import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { CommercialWorkspace } from "../components/CommercialWorkspace";
import { requireOperatorUi } from "../lib/access";

export const metadata: Metadata = { title: "Кабинет оператора" };

export default function OperatorPage() {
  requireOperatorUi();
  return <AppShell operator active="operator" eyebrow="Внутренний кабинет" title="Обзор бизнеса"><CommercialWorkspace /></AppShell>;
}
