/**
 * @param {string} value
 * @returns {string}
 */
export function clearZeroOnFocusValue(value) {
  return value === "0" ? "" : value;
}

/**
 * @param {string} value
 * @returns {number | null}
 */
export function parseNumericInput(value) {
  if (value.trim() === "") return null;

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
