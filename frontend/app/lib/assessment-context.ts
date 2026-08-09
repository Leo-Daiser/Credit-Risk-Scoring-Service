export interface AssessmentContext {
  amount: number;
  term: number;
  monthlyIncome: number;
  existingPayments: number;
}

let transientContext: AssessmentContext | null = null;

export function setTransientAssessmentContext(context: AssessmentContext): void {
  transientContext = { ...context };
}

export function consumeTransientAssessmentContext(): AssessmentContext | null {
  const context = transientContext;
  transientContext = null;
  return context;
}
