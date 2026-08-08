import { apiFetch } from "./api";

export type PublicEventType =
  | "landing_viewed"
  | "calculator_used"
  | "calculator_continue_clicked";

export function createAnonymousSessionId(): string {
  return `web-${crypto.randomUUID()}`;
}

export async function recordPublicEvent(
  eventType: PublicEventType,
  page: "landing" | "credit_calculator",
  anonymousSessionId: string,
): Promise<void> {
  await apiFetch("v1/analytics/public-event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: eventType,
      page,
      anonymous_session_id: anonymousSessionId,
    }),
  });
}
