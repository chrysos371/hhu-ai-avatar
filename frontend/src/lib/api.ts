export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export function readToken() {
  const fragment = window.location.hash.slice(1);
  if (/^[A-Za-z0-9_-]{20,200}$/.test(fragment)) {
    sessionStorage.setItem("avatar-token", fragment);
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
  }
  const token = sessionStorage.getItem("avatar-token");
  if (!token)
    throw new ApiError(
      403,
      "missing_token",
      "请使用启动终端提供的完整链接打开本机控制台。",
    );
  return token;
}
interface Options extends Omit<RequestInit, "body" | "headers"> {
  body?: unknown;
  headers?: Record<string, string>;
}
async function decode<T>(response: Response): Promise<T> {
  let value: { data: T; error: { code: string; message: string } | null };
  try {
    value = await response.json();
  } catch {
    throw new ApiError(
      response.status,
      "invalid_response",
      "服务响应无法读取，请检查服务状态。",
    );
  }
  if (!response.ok || value.error)
    throw new ApiError(
      response.status,
      value.error?.code ?? "request_failed",
      value.error?.message ?? "请求失败，请稍后重试。",
    );
  return value.data;
}
export async function apiRequest<T>(
  path: string,
  options: Options = {},
): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\"))
    throw new Error("仅支持控制台内部接口");
  const { body, headers, ...rest } = options;
  const response = await fetch("/api/v1" + path, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      "X-Avatar-Token": readToken(),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  return decode<T>(response);
}
export async function uploadKnowledge(file: File) {
  if (
    !/\.(txt|md)$/i.test(file.name) ||
    file.size === 0 ||
    file.size > 5 * 1024 * 1024
  )
    throw new ApiError(
      422,
      "invalid_file",
      "请选择不超过5 MiB的UTF-8 .txt或.md文件。",
    );
  const response = await fetch(
    "/api/v1/knowledge/preview-file?filename=" + encodeURIComponent(file.name),
    {
      method: "POST",
      headers: {
        "Content-Type": file.name.toLowerCase().endsWith(".md")
          ? "text/markdown"
          : "text/plain",
        "X-Avatar-Token": readToken(),
      },
      body: file,
      cache: "no-store",
    },
  );
  return decode<import("./types").KnowledgeDraft>(response);
}
export async function fetchSpeechAudio(id: string, signal: AbortSignal) {
  if (!/^[A-Za-z0-9_-]{20,100}$/.test(id)) throw new Error("音频标识无效");
  const response = await fetch("/api/v1/speech/audio/" + id, {
    headers: { "X-Avatar-Token": readToken() },
    cache: "no-store",
    signal,
  });
  if (!response.ok) await decode<never>(response);
  return response.blob();
}
export async function transcribeAudio(audio: Blob, signal: AbortSignal) {
  if (audio.size === 0 || audio.size > 6 * 1024 * 1024)
    throw new Error("请选择不超过 6 MiB、60 秒内的 PCM WAV 文件。");
  const response = await fetch("/api/v1/speech/transcribe", {
    method: "POST", body: audio, signal, cache: "no-store",
    headers: { "Content-Type": "audio/wav", "X-Avatar-Token": readToken() },
  });
  return decode<{ transcript: string }>(response);
}
export function formatTime(timestamp: number | null | undefined) {
  return timestamp == null || !Number.isFinite(timestamp)
    ? "—"
    : new Date(timestamp * 1000).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      });
}
