# Product acceptance walkthrough

This walkthrough verifies the client flow and internal business controls using only
synthetic offers. It does not require real partner credentials or customer data.

## 1. Prepare a controlled demo

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
python -m src.cli setup-demo --with-synthetic-events
python -m src.cli verify-demo
```

Open `http://localhost:3000`.

## 2. Public flow

1. Confirm that the landing page explains the two-minute calculation and comparison flow.
2. Open the calculator and change amount, term, rate, income, and existing payments.
3. Confirm that payment, repayment, overpayment, remaining budget, and debt load update
   without a network request.
4. Continue to offer matching and complete the approximate profile; optionally
   уточните возраст, доход и стаж.
5. Confirm that consent is empty by default and required before matching.
6. Confirm that the result contains Riskline Index, strengths and limiting factors,
   without raw probability or provider feature names.
7. Apply an improvement scenario and verify that payment, PTI, profile and eligible
   offer count change consistently.
8. Inspect the recommended offer-specific payment/rate/overpayment range, advertising
   label, partner warning, and compensation disclosure.
9. Start an offer transition and confirm the transparent partner-transition screen.

All synthetic offers must display `Демо-предложение` and must not imply real availability.

## 3. Recovery states

- Choose restrictive profile values and verify the calm no-offer guidance.
- Confirm suggestions to lower amount, increase term, consider refinancing, clarify
  unknown fields, and return later.
- Confirm loading, retry, and empty states without technical error details.

## 4. Operator business cockpit

Open the internal cabinet in local/demo mode and verify:

- applications, matches, impressions, partner transitions, CTR, partner outcomes,
  recorded revenue, and revenue per transition;
- recommended-card CTR and partner redirect failures;
- offer quality flags and segments without eligible offers;
- partner event journal without raw payloads;
- offer create/edit/deactivate and validation preview.

## 5. Public boundary

Run:

```powershell
python scripts/smoke_public_demo.py --base-url http://localhost:8000 --frontend-url http://localhost:3000 --mode public
```

The check must confirm that operator pages, internal diagnostics, server documentation,
metrics, and demo partner callbacks are unavailable in public mode.

## 6. Disclosure review

Before using a real offer, verify advertiser name, advertising label, legal text,
compensation disclosure, full-cost text when a rate is shown, public partner terms,
tracked redirect configuration, and ERID requirements. Do not invent missing legal data.
