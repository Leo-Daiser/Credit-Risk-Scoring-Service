import { notFound } from "next/navigation";
import { operatorUiAvailable } from "./access-policy.mjs";

export function requireOperatorUi(): void {
  if (!operatorUiAvailable(process.env)) notFound();
}
