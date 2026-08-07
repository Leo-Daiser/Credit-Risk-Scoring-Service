import type { NextRequest } from "next/server";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const backendBase = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  );
  const incoming = new URL(request.url);
  const target = new URL(`${backendBase}/${path.join("/")}`);
  target.search = incoming.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  const apiKey = process.env.API_KEY?.trim();
  if (apiKey) headers.set("X-API-Key", apiKey);

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : await request.arrayBuffer(),
      redirect: "manual",
    });
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
