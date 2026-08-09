import { apiFetch } from "./api";

export type PublicEventType =
  | "landing_viewed"
  | "assessment_started"
  | "assessment_step_completed"
  | "assessment_completed"
  | "calculator_used"
  | "calculator_continue_clicked"
  | "profile_started"
  | "profile_completed"
  | "profile_scored"
  | "profile_result_viewed"
  | "improvement_viewed"
  | "scenario_changed"
  | "scenario_started"
  | "scenario_applied"
  | "offers_viewed"
  | "recommended_offer_viewed"
  | "no_eligible_offers_viewed"
  | "offer_clicked"
  | "partner_transition_viewed";

export function createAnonymousSessionId(): string {
  return `web-${crypto.randomUUID()}`;
}

export async function recordPublicEvent(
  eventType: PublicEventType,
  page: "landing" | "assessment" | "credit_calculator" | "offers" | "result" | "scenario",
  anonymousSessionId: string,
  metadata: {
    profile_band?: string;
    pti_band?: string;
    scenario_type?: "amount" | "term" | "payments" | "refinance";
    offer_position?: "recommended" | "alternative";
    assessment_step?: 1 | 2 | 3 | 4;
  } = {},
): Promise<void> {
  await apiFetch("v1/analytics/public-event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: eventType,
      page,
      anonymous_session_id: anonymousSessionId,
      ...metadata,
    }),
  });
}
