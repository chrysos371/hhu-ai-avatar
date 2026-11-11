import { useState } from "react";
import type { ChatResult } from "../../lib/types";

export function ChatTrace({ trace }: { trace: ChatResult["trace"] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <details className="trace" onToggle={event => setExpanded(event.currentTarget.open)}>
      <summary>本轮决策与来源</summary>
      {expanded && <>
        {trace.guard?.guarded && <p className="notice">本轮由安全或现实边界规则直接回应。</p>}
        <h3>策略与状态</h3>
        <pre>{JSON.stringify(trace.decision, null, 2)}</pre>
        <h3>召回记忆</h3>
        <pre>{JSON.stringify(trace.recalled_memories, null, 2)}</pre>
        <h3>知识来源</h3>
        <pre>{JSON.stringify(trace.knowledge_sources ?? [], null, 2)}</pre>
        <h3>检查</h3>
        <pre>{JSON.stringify({ guard: trace.guard, verifier: trace.verifier }, null, 2)}</pre>
        <h3>工具调用</h3>
        <pre>{JSON.stringify(trace.tool_calls, null, 2)}</pre>
      </>}
    </details>
  );
}
