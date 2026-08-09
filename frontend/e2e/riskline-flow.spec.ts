import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const backendUrl = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8000";

async function completeAssessment(page: Page): Promise<void> {
  await page.goto("/assessment");
  await expect(page.getByLabel("Желаемая сумма, ₽")).toHaveValue("");
  await expect(page.getByLabel("Срок, месяцев")).toHaveValue("");
  await page.getByRole("button", { name: "Продолжить" }).click();
  await expect(page.getByRole("alert")).toContainText("Укажите примерную сумму");

  await page.getByLabel("Желаемая сумма, ₽").fill("300000");
  await page.getByLabel("Срок, месяцев").fill("36");
  await page.getByLabel("Цель кредита").selectOption("cash");
  await page.getByRole("button", { name: "Продолжить" }).click();

  await expect(page.getByLabel("Возраст, лет")).toHaveValue("");
  await page.getByLabel("Возраст, лет").fill("35");
  await page.getByLabel("Ваш регулярный доход в месяц, ₽").fill("180000");
  await page.getByLabel("Занятость").selectOption("employee");
  await page.getByLabel("Подтверждаемый стаж, лет").fill("8");
  await page.getByRole("button", { name: "Продолжить" }).click();

  await page.getByRole("button", { name: "Нет" }).click();
  await page.getByLabel("Кредитная история — по вашей оценке").selectOption("good");
  await page.getByRole("button", { name: "Продолжить" }).click();

  const consent = page.getByLabel(/Согласен на обработку/);
  await expect(consent).not.toBeChecked();
  await page.getByRole("button", { name: "Получить оценку" }).click();
  await expect(page.getByRole("alert")).toContainText("согласие");
  await consent.check();
  await page.getByRole("button", { name: "Получить оценку" }).click();
  await expect(page.getByRole("heading", { name: "Ваша оценка Riskline" })).toBeVisible();
}

test.beforeEach(async ({ request }) => {
  const ready = await request.get(`${backendUrl}/ready`);
  expect(ready.ok()).toBeTruthy();
});

test("primary assessment, ML result, scenario and tracked transition", async ({ page, request }) => {
  const status = await (await request.get(`${backendUrl}/ready`)).json();
  if (!status.public_model_available && process.env.E2E_REQUIRE_ML === "false") {
    test.skip(true, "GitHub CI has no gitignored trusted model artifact");
  }
  expect(status.public_model_available, "Full demo E2E requires Public Profile ML").toBe(true);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/финансов.*профил/i);
  await page.locator('a[href="/assessment"]:visible').first().click();
  await completeAssessment(page);

  await expect(page.locator(".riskline-index strong")).not.toHaveText("—");
  await expect(page.getByRole("heading", { name: "Что влияет на текущий сценарий" })).toBeVisible();
  await expect(page.locator(".public-workspace")).not.toContainText(/CatBoost|SHAP|default_probability|AMT_CREDIT/);

  const scenarioButton = page.locator(".improvement-grid article button").first();
  if (await scenarioButton.isVisible()) {
    await scenarioButton.click();
    await expect(page.getByLabel("Сравнение сценариев")).toBeVisible();
  }

  const recommended = page.locator("#recommended-offer");
  await expect(recommended).toBeVisible();
  await recommended.getByRole("button").click();
  const dialog = page.getByRole("dialog", { name: "Вы переходите к партнёру" });
  await expect(dialog).toContainText("Условия и решение определяет партнёр");
  await expect(dialog).toContainText("может получить вознаграждение");
  await expect(dialog.getByRole("button", { name: /Продолжить у партнёра/ })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("calculator handoff is transient and does not persist financial values", async ({ page, context }) => {
  await page.goto("/score");
  await page.getByLabel("Сумма, ₽").fill("420000");
  await page.getByLabel("Срок, месяцев").fill("48");
  await page.getByLabel("Ваш регулярный доход в месяц, ₽").fill("145000");
  await page.getByLabel("Текущие кредитные платежи, ₽").fill("9000");
  await page.getByRole("button", { name: /Оценить профиль и подобрать предложения/ }).click();

  await expect(page).toHaveURL(/\/assessment$/);
  await expect(page.getByLabel("Желаемая сумма, ₽")).toHaveValue("420000");
  await expect(page.getByLabel("Срок, месяцев")).toHaveValue("48");
  expect(new URL(page.url()).search).toBe("");
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
  expect((await context.cookies()).length).toBe(0);
  expect(await page.evaluate(async () => (await indexedDB.databases()).length)).toBe(0);
});

test("public pages have no serious accessibility violations or horizontal overflow", async ({ page }, testInfo) => {
  for (const route of ["/", "/assessment", "/score"]) {
    await page.goto(route);
    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${testInfo.project.name} ${route} horizontal overflow`).toBeLessThanOrEqual(1);
  }
});
