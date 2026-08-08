import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  calculateAnnuity,
  calculatePrincipal,
} from "../app/lib/credit-calculator.mjs";

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

test("server-renders the product dashboard without starter metadata", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Обзор · Riskline<\/title>/i);
  assert.match(html, /Решения по риску/);
  assert.match(html, /Оценить заявку/);
  assert.match(html, /Пакетный скоринг/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("all primary operator routes render their product-specific first view", async () => {
  const cases = [
    ["/score", /Оцените кредитную нагрузку до заявки/],
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

test("personal score route starts with a questionnaire and keeps JSON in expert mode", async () => {
  const response = await render("/score");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Для себя/);
  assert.match(html, /Сумма кредита/);
  assert.match(html, /Доход в месяц/);
  assert.match(html, /Комфортная сумма кредита/);
  assert.match(html, /Экспертный JSON/);
  assert.match(html, /не является офертой, кредитным решением/);
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
  assert.match(page, /DashboardClient/);
});
