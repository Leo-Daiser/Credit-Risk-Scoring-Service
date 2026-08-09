import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  calculateAnnuity,
  calculateCreditScenario,
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
import {
  buildOfferPayload,
  initialOfferDraft,
  validateOfferDraft,
} from "../app/lib/offer-management.mjs";

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
  assert.match(html, /Рассчитать платёж/);
  assert.match(html, /Проверьте кредитную нагрузку и подберите подходящие предложения без паспорта и звонков/);
  assert.match(html, /СНИЛС и ИНН/);
  assert.match(html, /Название работодателя/);
  assert.match(html, /Сервис не принимает кредитных решений/);
  assert.match(html, /Финальное решение принимает банк/);
  assert.doesNotMatch(html, /гарантируем одобрение|точно знаем, какой банк одобрит|банковский скоринг|официальное решение/i);
  assert.doesNotMatch(html, /Пакетный скоринг|Коммерческая аналитика|История/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("public and enabled local operator routes render their first view", async () => {
  const cases = [
    ["/score", /Рассчитайте платёж и долговую нагрузку/],
    ["/offers", /Предварительный профиль и совместимые предложения/],
    ["/operator", /Решения по риску/],
    ["/operator/score", /Оцените кредитную нагрузку до заявки/],
    ["/operator/offers", /Каталог без ручного редактирования YAML/],
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
  assert.match(html, /Всего к возврату/);
  assert.match(html, /Переплата/);
  assert.match(html, /Долговая нагрузка/);
  assert.match(html, /Продолжить к privacy-light подбору/);
  assert.doesNotMatch(html, /Экспертный JSON|Feature payload|audit log/);
});

test("public deployment blocks operator BFF paths and unknown proxy paths", () => {
  assert.equal(classifyBackendRequest("v1/offers/match", "POST"), "public");
  assert.equal(classifyBackendRequest("v1/offers/42/click", "POST"), "public");
  assert.equal(classifyBackendRequest("v1/analytics/public-event", "POST"), "public");
  assert.equal(classifyBackendRequest("v1/analytics/commercial-summary", "GET"), "operator");
  assert.equal(classifyBackendRequest("v1/operator/offers", "GET"), "operator");
  assert.equal(classifyBackendRequest("v1/operator/offers", "POST"), "operator");
  assert.equal(classifyBackendRequest("v1/operator/offers/42", "PATCH"), "operator");
  assert.equal(classifyBackendRequest("v1/operator/offers/42/deactivate", "POST"), "operator");
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
    "../app/operator/offers/page.tsx",
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

test("operator offer create and edit draft validation rejects unsafe values", () => {
  const valid = {
    ...initialOfferDraft,
    bankId: "demo-managed",
    productName: "Managed Cash Offer",
    advertiserName: "Demo advertiser",
  };
  assert.deepEqual(validateOfferDraft(valid), []);
  const payload = buildOfferPayload(valid);
  assert.equal(payload.bank_id, "demo-managed");
  assert.equal(payload.affiliate_url_template_key, null);
  assert.ok(!Object.hasOwn(payload, "affiliate_url_template"));

  const invalidRange = validateOfferDraft({ ...valid, minAmount: "500000", maxAmount: "100000" });
  assert.ok(invalidRange.some((item) => /диапазон суммы/i.test(item)));
  const unsafeKey = validateOfferDraft({ ...valid, partnerId: "real", affiliateTemplateKey: "https://partner/?token=secret" });
  assert.ok(unsafeKey.some((item) => /env-key/i.test(item)));
});

test("operator offer page renders table states and protected actions without secret fields", async () => {
  const response = await render("/operator/offers");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Управление офферами/);
  assert.match(html, /Загружаем каталог/);
  assert.match(html, /Предварительная проверка/);
  assert.match(html, /Affiliate template env key/);
  assert.doesNotMatch(html, /PARTNER_POSTBACK_SECRET|affiliate_url_template[^_]|private token/i);

  const source = await readFile(
    new URL("../app/components/OfferManagementWorkspace.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /\/deactivate/);
  assert.match(source, /"PATCH"/);
  assert.match(source, /window\.confirm/);
  assert.doesNotMatch(source, /localStorage|sessionStorage/);
});

test("credit calculator computes repayment, overpayment, PTI and high-load band locally", () => {
  const scenario = calculateCreditScenario(120_000, 0, 12, 5_000, 20_000);
  assert.equal(scenario.payment, 10_000);
  assert.equal(scenario.totalRepayment, 120_000);
  assert.equal(scenario.overpayment, 0);
  assert.equal(scenario.pti, 0.75);
  assert.equal(scenario.affordabilityBand, "high");
});

test("privacy-light offer matching exposes consent and advertising boundaries", async () => {
  const response = await render("/offers");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Паспорт, телефон, имя, документы, работодатель и данные БКИ не запрашиваются/);
  assert.match(html, /Согласен на обработку введённых диапазонов/);
  assert.match(html, /не принимает кредитных решений/);
  assert.match(html, /Точные суммы используются только в текущем запросе/);
  assert.match(html, /Финальное решение принимает банк/);
  assert.match(html, /Можно указать примерные значения/);
  assert.match(html, /Точная сумма, ₽ — необязательно/);
  assert.match(html, /Кредитная история/);
  assert.match(html, /Что такое долговая нагрузка/);
  assert.match(html, /Почему результат предварительный/);
  assert.doesNotMatch(html, /Имя пользователя|Номер телефона|Паспортные данные/);
  assert.doesNotMatch(html, /localStorage|sessionStorage/);
});

test("SEO-ready public guides render metadata, useful copy and CTA", async () => {
  const cases = [
    ["/credit-calculator", /Калькулятор кредита по сумме и сроку/],
    ["/debt-load-calculator", /Как оценить долговую нагрузку/],
    ["/loan-by-income", /Какой платёж комфортен при вашем доходе/],
    ["/refinance-check", /Когда рефинансирование может иметь смысл/],
    ["/credit-history-guide", /Почему кредитная история влияет на решение банка/],
  ];
  for (const [path, expected] of cases) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    const html = await response.text();
    assert.match(html, expected, path);
    assert.match(html, /<meta name="description" content="[^"]+"/i, path);
    assert.match(html, /Финальное решение и индивидуальные условия определяет банк/, path);
    assert.doesNotMatch(html, /гарантированное одобрение|гарантируем одобрение|официальное решение/i, path);
  }
});

test("public calculation and transient matching values are never persisted in browser storage", async () => {
  const [calculator, offers, analytics] = await Promise.all([
    readFile(new URL("../app/components/CalculatorWorkspace.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/OfferWorkspace.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/lib/public-analytics.ts", import.meta.url), "utf8"),
  ]);
  assert.doesNotMatch(`${calculator}${offers}${analytics}`, /localStorage|sessionStorage/);
  assert.match(calculator, /calculateCreditScenario/);
  assert.match(calculator, /continueToMatching/);
  assert.doesNotMatch(analytics, /amount|income|payment|debt|rate/i);
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
