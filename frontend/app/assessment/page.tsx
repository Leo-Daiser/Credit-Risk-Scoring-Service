import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { OfferWorkspace } from "../components/OfferWorkspace";

export const metadata: Metadata = {
  title: "Оценка финансового профиля",
  description:
    "Получите персональную оценку Riskline, объяснение факторов, сценарии улучшения и подходящие предложения без паспорта и телефона.",
};

export default function AssessmentPage() {
  return (
    <AppShell active="assessment" eyebrow="Оценка профиля" title="Оценка Riskline">
      <OfferWorkspace showModelStatus={process.env.APP_ENV !== "public"} />
    </AppShell>
  );
}
