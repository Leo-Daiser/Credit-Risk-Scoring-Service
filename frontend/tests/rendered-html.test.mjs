import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  calculateAnnuity,
  calculatePrincipal,
} from "../app/lib/credit-calculator.mjs";
import {
  clearZeroOnFocusValue,
  parseNumericInput,
} from "../app/lib/numeric-input.mjs";
import {
  buildPersonalFeatures,
  initialPersonalForm,
  parsePersonalFormDraft,
} from "../app/lib/personal-score.ts";
import {
  classifyBackendRequest,
  operatorUiAvailable,
} from "../app/lib/access-policy.mjs";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${path}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    {
      ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
    },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the public landing without operator data", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Предварительный подбор кредитных предложений · Riskline<\/title>/i);
  assert.match(html, /Privacy-light/);
  assert.match(html, /Демонстрационный режим/);
  assert.match(html, /Открыть калькулятор/);
  assert.match(html, /финальное решение по заявке всегда принимает банк/i);
  assert.doesNotMatch(html, /Пакетный скоринг|Коммерческая аналитика|История/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("public and enabled local operator routes render their first view", async () => {
  const cases = [
    ["/score", /Рассчитайте платёж и долговую нагрузку/],
    ["/offers", /Сначала допустимость\. Затем рейтинг/],
    ["/operator", /Решения по риску/],
    ["/operator/score", /Оцените кредитную нагрузку до заявки/],
    ["/commercial", /Воронка, качество офферов и неудовлетворённый спрос/],
    ["/batches", /Реестр вошёл\. Решения вышли/],
    ["/history", /Каждое решение можно восстановить/],
    ["/model", /Версия модели — часть каждого решения/],
  ];

  for (const [path, expected] of cases) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    assert.match(await response.text(), expected, path);
  }
});

test("operator score route keeps the internal model questionnaire and JSON mode", async () => {
  const response = await render("/operator/score");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Для себя/);
  assert.match(html, /Сумма кредита/);
  assert.match(html, /Доход в месяц/);
  assert.match(html, /Комфортная сумма кредита/);
  assert.match(html, /Экспертный JSON/);
  assert.match(html, /не является офертой, кредитным решением/);
});

test("public calculator does not expose raw model or operator controls", async () => {
  const response = await render("/score");
  const html = await response.text();
  assert.match(html, /Публичный калькулятор/);
  assert.match(html, /без отправки данных/);
  assert.doesNotMatch(html, /Экспертный JSON|Feature payload|audit log/);
});

test("public deployment blocks operator BFF paths and unknown proxy paths", () => {
  assert.equal(classifyBackendRequest("v1/offers/match", "POST"), "public");
  assert.equal(classifyBackendRequest("v1/offers/42/click", "POST"), "public");
  assert.equal(classifyBackendRequest("v1/analytics/commercial-summary", "GET"), "operator");
  assert.equal(classifyBackendRequest("v1/partner/postback", "POST"), "deny");
  assert.equal(classifyBackendRequest("arbitrary/internal", "GET"), "deny");
  assert.equal(operatorUiAvailable({ APP_ENV: "public", OPERATOR_UI_ENABLED: "true" }), false);
  assert.equal(operatorUiAvailable({ APP_ENV: "demo", OPERATOR_UI_ENABLED: "true" }), true);
  assert.equal(operatorUiAvailable({ APP_ENV: "dev", OPERATOR_UI_ENABLED: "true" }), true);
  assert.equal(operatorUiAvailable({ APP_ENV: "unexpected", OPERATOR_UI_ENABLED: "true" }), false);
});

test("every operator page applies the shared server-side UI guard", async () => {
  const pages = [
    "../app/operator/page.tsx",
    "../app/operator/score/page.tsx",
    "../app/commercial/page.tsx",
    "../app/batches/page.tsx",
    "../app/history/page.tsx",
    "../app/model/page.tsx",
  ];
  for (const page of pages) {
    assert.match(await readFile(new URL(page, import.meta.url), "utf8"), /requireOperatorUi\(\)/);
  }
});

test("credit calculator handles zero and non-zero rates consistently", () => {
  assert.equal(calculateAnnuity(120_000, 0, 12), 10_000);
  assert.equal(calculatePrincipal(10_000, 0, 12), 120_000);

  const payment = calculateAnnuity(1_000_000, 12, 24);
  assert.ok(Math.abs(payment - 47_073.47) < 0.01);
  assert.ok(Math.abs(calculatePrincipal(payment, 12, 24) - 1_000_000) < 0.01);
  assert.equal(calculateAnnuity(0, 12, 24), 0);
  assert.equal(calculatePrincipal(-1, 12, 24), 0);
});

test("privacy-light offer matching exposes consent and advertising boundaries", async () => {
  const response = await render("/offers");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Паспорт, телефон, адрес и данные БКИ не нужны/);
  assert.match(html, /Согласен на обработку диапазонов/);
  assert.match(html, /не принимает кредитных решений/);
  assert.match(html, /Точные суммы не сохраняются/);
  assert.match(html, /Финальное решение принимает банк/);
  assert.match(html, /предварительно оценит платёж и долговую нагрузку/);
  assert.doesNotMatch(html, /localStorage|sessionStorage/);
});

test("commercial operator view renders protected analytics sections and safe states", async () => {
  const response = await render("/commercial");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Commercial Analytics/);
  assert.match(html, /Offer Quality/);
  assert.match(html, /Segment Opportunities/);
  assert.match(html, /Event Debug/);
  assert.match(html, /Загружаем агрегаты/);
  assert.match(html, /Пока пусто/);
  assert.doesNotMatch(html, /X-API-Key|API_KEY=|localStorage|sessionStorage/);

  const source = await readFile(
    new URL("../app/components/CommercialWorkspace.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /Коммерческая аналитика недоступна/);
  assert.match(source, /Raw payload намеренно не отображается/);
});

test("numeric inputs clear a displayed zero without coercing an empty edit", () => {
  let editedValue = clearZeroOnFocusValue("0");
  assert.equal(editedValue, "");
  assert.equal(parseNumericInput(editedValue), null);

  editedValue = "150000";
  assert.equal(parseNumericInput(editedValue), 150_000);
  assert.equal(clearZeroOnFocusValue("19.9"), "19.9");
  assert.equal(parseNumericInput("-0.5"), -0.5);
});

test("numeric form keeps an intentional zero and builds a numeric model payload", () => {
  const parsed = parsePersonalFormDraft({
    ...initialPersonalForm,
    currentDebtPayment: "0",
    employmentYears: "0",
  });

  assert.ok(parsed.form);
  assert.equal(parsed.form.currentDebtPayment, 0);
  assert.equal(parsed.form.employmentYears, 0);

  const features = buildPersonalFeatures(parsed.form, 24_000);
  assert.equal(typeof features.AMT_INCOME_TOTAL, "number");
  assert.equal(typeof features.AMT_CREDIT, "number");
  assert.equal(typeof features.AMT_ANNUITY, "number");
  assert.equal(typeof features.DAYS_EMPLOYED, "number");
});

test("an empty numeric draft remains invalid instead of silently becoming zero", () => {
  const parsed = parsePersonalFormDraft({
    ...initialPersonalForm,
    monthlyIncome: "",
  });

  assert.equal(parsed.form, null);
  assert.match(parsed.error, /Доход в месяц/);
});

test("starter preview and unused persistence dependencies are removed", async () => {
  const [packageJson, page, hosting] = await Promise.all([
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../.openai/hosting.json", import.meta.url), "utf8"),
  ]);
  assert.doesNotMatch(packageJson, /react-loading-skeleton|drizzle-orm/);
  assert.doesNotMatch(page, /_sites-preview|codex-preview/);
  assert.deepEqual(JSON.parse(hosting), { d1: null, r2: null });
  assert.match(packageJson, /riskline-console/);
  assert.match(page, /Предварительный подбор/);
});
