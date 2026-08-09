import type { Metadata } from "next";
import { AppShell } from "../../components/AppShell";
import { OfferManagementWorkspace } from "../../components/OfferManagementWorkspace";
import { requireOperatorUi } from "../../lib/access";

export const metadata: Metadata = {
  title: "Управление офферами · Riskline",
  description: "Защищённое управление каталогом кредитных предложений.",
};

export default function OperatorOffersPage() {
  requireOperatorUi();
  return (
    <AppShell
      operator
      active="offerManagement"
      eyebrow="Operator · catalog"
      title="Управление офферами"
    >
      <OfferManagementWorkspace />
    </AppShell>
  );
}
