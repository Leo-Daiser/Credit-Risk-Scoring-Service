"use client";

import { useEffect, useState } from "react";
import { createAnonymousSessionId, recordPublicEvent } from "../lib/public-analytics";

export function PublicEventTracker() {
  const [sessionId] = useState(createAnonymousSessionId);

  useEffect(() => {
    void recordPublicEvent("landing_viewed", "landing", sessionId).catch(() => undefined);
  }, [sessionId]);

  return null;
}
