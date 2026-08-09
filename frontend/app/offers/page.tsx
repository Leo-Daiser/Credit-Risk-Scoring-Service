import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import { OfferWorkspace } from "../components/OfferWorkspace";

export const metadata: Metadata = {
  title: "Подбор кредитных предложений",
  description: "Предварительный подбор подходящих кредитных предложений по примерным параметрам.",
};

export default function OffersPage() {
  return (
    <AppShell active="offers" eyebrow="Сравнение условий" title="Подбор предложений">
      <OfferWorkspace />
    </AppShell>
  );
}
