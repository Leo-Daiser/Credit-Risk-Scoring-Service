import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { DashboardClient } from "../components/DashboardClient";
import { requireOperatorUi } from "../lib/access";

export const metadata: Metadata = { title: "Операторский обзор" };

export default function OperatorPage() {
  requireOperatorUi();
  return <AppShell operator active="operator" eyebrow="Операционный центр" title="Кредитный риск"><DashboardClient /></AppShell>;
}
