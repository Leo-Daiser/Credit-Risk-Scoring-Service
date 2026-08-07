import type { Metadata } from "next";
import { AppShell } from "./components/AppShell";
import { DashboardClient } from "./components/DashboardClient";

export const metadata: Metadata = {
  title: "Обзор",
  description:
    "Сводка по решениям, пакетным заданиям и текущей версии модели.",
};

export default function Home() {
  return (
    <AppShell active="overview" eyebrow="Операционный центр" title="Кредитный риск">
      <DashboardClient />
    </AppShell>
  );
}
