import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

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
    ["/score", /Проверьте риск до принятия решения/],
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
