import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { OfferWorkspace } from "../components/OfferWorkspace";

export const metadata: Metadata = {
  title: "Подбор кредитных предложений",
  description: "Предварительный privacy-light профиль и подбор рекламных предложений.",
};

export default function OffersPage() {
  return (
    <AppShell active="offers" eyebrow="Privacy-light · Offer matching" title="Подбор предложений">
      <OfferWorkspace />
    </AppShell>
  );
}
