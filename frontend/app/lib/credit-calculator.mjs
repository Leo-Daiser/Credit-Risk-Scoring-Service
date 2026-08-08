/**
 * Calculate a monthly annuity payment without commissions or insurance.
 *
 * @param {number} principal
 * @param {number} annualRate
 * @param {number} months
 * @returns {number}
 */
export function calculateAnnuity(principal, annualRate, months) {
  if (principal <= 0 || months <= 0) return 0;
  const monthlyRate = annualRate / 100 / 12;
  if (monthlyRate === 0) return principal / months;
  return principal * monthlyRate / (1 - (1 + monthlyRate) ** -months);
}

/**
 * Calculate the principal supported by a monthly annuity payment.
 *
 * @param {number} payment
 * @param {number} annualRate
 * @param {number} months
 * @returns {number}
 */
export function calculatePrincipal(payment, annualRate, months) {
  if (payment <= 0 || months <= 0) return 0;
  const monthlyRate = annualRate / 100 / 12;
  if (monthlyRate === 0) return payment * months;
  return payment * (1 - (1 + monthlyRate) ** -months) / monthlyRate;
}

/**
 * Build a complete browser-only credit scenario.
 * @param {number} principal
 * @param {number} annualRate
 * @param {number} months
 * @param {number} existingPayments
 * @param {number} monthlyIncome
 */
export function calculateCreditScenario(
  principal,
  annualRate,
  months,
  existingPayments,
  monthlyIncome,
) {
  const payment = calculateAnnuity(principal, annualRate, months);
  const totalRepayment = payment * months;
  const overpayment = Math.max(0, totalRepayment - principal);
  const allMonthlyPayments = payment + existingPayments;
  const pti = monthlyIncome > 0 ? allMonthlyPayments / monthlyIncome : null;
  const affordabilityBand = pti === null
    ? "unknown"
    : pti <= 0.3
      ? "comfortable"
      : pti <= 0.5
        ? "manageable"
        : pti <= 0.7
          ? "stretched"
          : "high";
  return { payment, totalRepayment, overpayment, allMonthlyPayments, pti, affordabilityBand };
}
