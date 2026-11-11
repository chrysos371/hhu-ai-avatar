import { ApiError, apiRequest, readToken } from "./api";
import type { ChatResult } from "./types";

export interface ExpectedContext { instance_id: string; revision: number; context_cursor: number }
export interface TurnInput { request_id: string; text: string; use_web: boolean; expected_context?: ExpectedContext }
export async function cancelTurn(id: string) {
  return apiRequest("/turns/" + encodeURIComponent(id) + "/cancel", {
    method: "POST", body: {}, keepalive: true,
  });
}

export async function streamTurn(input: TurnInput, signal: AbortSignal, onText: (text: string) => void): Promise<ChatResult> {
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const job = await apiRequest<{ job_id: string }>("/turns", { method: "POST", body: input, signal });
    if (signal.aborted) throw new DOMException("已停止", "AbortError");
    const response = await fetch("/api/v1/turns/" + encodeURIComponent(job.job_id) + "/events", {
      headers: { "X-Avatar-Token": readToken() }, signal, cache: "no-store",
    });
    if (!response.ok || !response.body) throw new ApiError(response.status, "stream_unavailable", "无法连接本轮进度，请重试。");
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (signal.aborted) throw new DOMException("已停止", "AbortError");
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 2 * 1024 * 1024) throw new Error("本轮事件超过可读取范围。");
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const block = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        let event = "message";
        const data: string[] = [];
        for (const line of block.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        }
        if (!data.length) continue;
        const payload = JSON.parse(data.join("\n"));
        if (event === "text" && typeof payload.text === "string") onText(payload.text);
        if (event === "result") {
          if (typeof payload.reply !== "string") throw new Error("本轮结果格式无效。");
          return payload as ChatResult;
        }
        if (event === "cancelled") throw new DOMException("本轮已停止", "AbortError");
        if (event === "error") throw new ApiError(500, payload.code ?? "turn_failed", payload.message ?? "本轮处理失败。");
      }
      if (done) throw new Error("连接已中断；本轮不会自动重复发送。");
    }
  } catch (error) {
    void cancelTurn(input.request_id).catch(() => {});
    throw error;
  } finally {
    await reader?.cancel().catch(() => {});
  }
}
