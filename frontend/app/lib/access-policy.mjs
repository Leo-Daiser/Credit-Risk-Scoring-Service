const PUBLIC_BACKEND_ROUTES = [
  { method: "POST", pattern: /^v1\/profile\/score$/ },
  { method: "POST", pattern: /^v1\/offers\/match$/ },
  { method: "POST", pattern: /^v1\/offers\/\d+\/click$/ },
  { method: "POST", pattern: /^v1\/analytics\/public-event$/ },
];

const OPERATOR_BACKEND_ROUTES = [
  { method: "POST", pattern: /^score$/ },
  { method: "GET", pattern: /^(model_info|feature_schema)$/ },
  { method: "GET", pattern: /^v1\/dashboard$/ },
  { method: "GET", pattern: /^v1\/scoring\/history$/ },
  { method: "GET", pattern: /^v1\/offers$/ },
  { method: "GET", pattern: /^v1\/analytics\/(commercial-summary|segment-opportunities|event-debug)$/ },
  { method: "GET", pattern: /^v1\/offers\/quality-report$/ },
  { method: "GET", pattern: /^v1\/batch\/(jobs(?:\/[^/]+(?:\/result)?)?|template\.csv)$/ },
  { method: "POST", pattern: /^v1\/batch\/jobs$/ },
];

export function deploymentMode(env = {}) {
  const value = String(env.APP_ENV ?? "local").trim().toLowerCase();
  const normalized = {
    dev: "local",
    development: "local",
    prod: "public",
    production: "public",
  }[value] ?? value;
  return ["local", "demo", "public"].includes(normalized) ? normalized : "public";
}

export function operatorUiAvailable(env = {}) {
  if (deploymentMode(env) === "public") return false;
  const configured = String(env.OPERATOR_UI_ENABLED ?? "true").trim().toLowerCase();
  return configured === "true" || configured === "1";
}

export function classifyBackendRequest(path, method) {
  const normalizedPath = String(path).replace(/^\/+|\/+$/g, "");
  const normalizedMethod = String(method).toUpperCase();
  if (
    PUBLIC_BACKEND_ROUTES.some(
      (route) => route.method === normalizedMethod && route.pattern.test(normalizedPath),
    )
  ) return "public";
  if (
    OPERATOR_BACKEND_ROUTES.some(
      (route) => route.method === normalizedMethod && route.pattern.test(normalizedPath),
    )
  ) return "operator";
  return "deny";
}
