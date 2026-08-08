import type { NextRequest } from "next/server";
import { classifyBackendRequest, operatorUiAvailable } from "../../../lib/access-policy.mjs";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const backendPath = path.join("/");
  const access = classifyBackendRequest(backendPath, request.method);
  if (access === "deny" || (access === "operator" && !operatorUiAvailable(process.env))) {
    return Response.json({ detail: "Not found." }, { status: 404 });
  }
  const backendBase = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  );
  const incoming = new URL(request.url);
  const target = new URL(`${backendBase}/${backendPath}`);
  target.search = incoming.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  headers.delete("x-api-key");
  headers.delete("authorization");
  headers.delete("cookie");
  if (access === "operator") {
    const apiKey = process.env.API_KEY?.trim();
    if (!apiKey) {
      return Response.json(
        { detail: "Operator BFF is not configured." },
        { status: 503 },
      );
    }
    headers.set("X-API-Key", apiKey);
  }

  try {
    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const upstreamInit: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      redirect: "manual",
    };
    if (hasBody && request.body) upstreamInit.duplex = "half";

    const upstream = await fetch(target, upstreamInit);
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.delete("content-length");
    responseHeaders.delete("transfer-encoding");
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { detail: "Сервис скоринга сейчас недоступен. Проверьте состояние API." },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
