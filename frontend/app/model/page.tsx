import { redirect } from "next/navigation";
import { requireOperatorUi } from "../lib/access";

export default function LegacySystemPage() {
  requireOperatorUi();
  redirect("/operator/system");
}
