import { parseNumericInput } from "./numeric-input.mjs";

export type FeatureValue = string | number | boolean | null;

export interface PersonalFormDraft {
  monthlyIncome: string;
  creditAmount: string;
  termMonths: string;
  annualRate: string;
  currentDebtPayment: string;
  comfortableShare: string;
  age: string;
  employmentYears: string;
  children: string;
  familyMembers: string;
  contractType: string;
  incomeType: string;
  housingType: string;
  ownsCar: boolean;
  ownsRealty: boolean;
}

export interface PersonalForm {
  monthlyIncome: number;
  creditAmount: number;
  termMonths: number;
  annualRate: number;
  currentDebtPayment: number;
  comfortableShare: number;
  age: number;
  employmentYears: number;
  children: number;
  familyMembers: number;
  contractType: string;
  incomeType: string;
  housingType: string;
  ownsCar: boolean;
  ownsRealty: boolean;
}

export type NumericField = {
  [Key in keyof PersonalFormDraft]: PersonalFormDraft[Key] extends string
    ? Key extends "contractType" | "incomeType" | "housingType"
      ? never
      : Key
    : never;
}[keyof PersonalFormDraft];

export const initialPersonalForm: PersonalFormDraft = {
  monthlyIncome: "120000",
  creditAmount: "800000",
  termMonths: "36",
  annualRate: "19.9",
  currentDebtPayment: "12000",
  comfortableShare: "35",
  age: "34",
  employmentYears: "7",
  children: "1",
  familyMembers: "3",
  contractType: "Cash loans",
  incomeType: "Working",
  housingType: "House / apartment",
  ownsCar: false,
  ownsRealty: true,
};

const numericFieldLabels: Record<NumericField, string> = {
  monthlyIncome: "Доход в месяц",
  creditAmount: "Сумма кредита",
  termMonths: "Срок",
  annualRate: "Ставка",
  currentDebtPayment: "Другие кредитные платежи",
  comfortableShare: "Комфортная доля платежей",
  age: "Возраст",
  employmentYears: "Стаж",
  children: "Детей",
  familyMembers: "Членов семьи",
};

export function numericValue(value: string): number {
  return parseNumericInput(value) ?? 0;
}

export function parsePersonalFormDraft(
  draft: PersonalFormDraft,
): { form: PersonalForm; error: null } | { form: null; error: string } {
  const parsed = {} as Record<NumericField, number>;

  for (const field of Object.keys(numericFieldLabels) as NumericField[]) {
    const value = parseNumericInput(draft[field]);
    if (value === null) {
      return { form: null, error: `Заполните числовое поле «${numericFieldLabels[field]}».` };
    }
    parsed[field] = value;
  }

  return {
    form: {
      ...parsed,
      contractType: draft.contractType,
      incomeType: draft.incomeType,
      housingType: draft.housingType,
      ownsCar: draft.ownsCar,
      ownsRealty: draft.ownsRealty,
    },
    error: null,
  };
}

export function validatePersonalForm(form: PersonalForm): string | null {
  if (form.monthlyIncome < 10_000) return "Укажите ежемесячный доход не менее 10 000 ₽.";
  if (form.creditAmount < 10_000) return "Укажите сумму кредита не менее 10 000 ₽.";
  if (form.termMonths < 3 || form.termMonths > 360) return "Срок кредита должен быть от 3 до 360 месяцев.";
  if (form.annualRate < 0 || form.annualRate > 100) return "Ставка должна быть от 0% до 100%.";
  if (form.currentDebtPayment < 0) return "Текущие платежи не могут быть отрицательными.";
  if (form.age < 18 || form.age > 75) return "Возраст должен быть от 18 до 75 лет.";
  if (form.employmentYears < 0 || form.employmentYears > form.age - 14) {
    return "Стаж не может быть отрицательным или превышать возраст за вычетом 14 лет.";
  }
  if (form.children < 0 || form.familyMembers < 1 || form.familyMembers < form.children + 1) {
    return "Число членов семьи должно быть больше числа детей.";
  }
  return null;
}

export function buildPersonalFeatures(
  form: PersonalForm,
  annuity: number,
): Record<string, FeatureValue> {
  const annualIncome = form.monthlyIncome * 12;
  const daysBirth = -Math.round(form.age * 365.25);
  const daysEmployed = -Math.round(form.employmentYears * 365.25);

  return {
    AMT_INCOME_TOTAL: annualIncome,
    AMT_CREDIT: form.creditAmount,
    AMT_ANNUITY: Math.round(annuity),
    AGE_YEARS: form.age,
    DAYS_BIRTH: daysBirth,
    EMPLOYMENT_YEARS: form.employmentYears,
    DAYS_EMPLOYED: daysEmployed,
    CNT_CHILDREN: form.children,
    CNT_FAM_MEMBERS: form.familyMembers,
    NAME_CONTRACT_TYPE: form.contractType,
    NAME_INCOME_TYPE: form.incomeType,
    NAME_HOUSING_TYPE: form.housingType,
    FLAG_OWN_CAR: form.ownsCar ? "Y" : "N",
    FLAG_OWN_REALTY: form.ownsRealty ? "Y" : "N",
    CREDIT_INCOME_RATIO: form.creditAmount / annualIncome,
    ANNUITY_INCOME_RATIO: annuity / annualIncome,
    CREDIT_TERM: annuity / form.creditAmount,
    DAYS_EMPLOYED_RATIO: daysEmployed / daysBirth,
    INCOME_PER_FAM_MEMBER: annualIncome / form.familyMembers,
  };
}
