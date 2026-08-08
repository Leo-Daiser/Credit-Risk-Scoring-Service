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
