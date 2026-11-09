import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, Upload } from "lucide-react";
import { apiRequest, formatTime, uploadKnowledge } from "../../lib/api";
import type {
  KnowledgeDraft,
  KnowledgeResult,
  KnowledgeSource,
} from "../../lib/types";
import {
  ErrorMessage,
  PageHeading,
  QueryState,
} from "../../components/QueryState";
import { useDraftDialog } from "../../components/OperationConfirmDialog";
export function KnowledgePage() {
  const sources = useQuery({
    queryKey: ["knowledge-sources"],
    queryFn: () => apiRequest<KnowledgeSource[]>("/knowledge/sources"),
  });
  const [mode, setMode] = useState<"text" | "file">("text");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<KnowledgeDraft | null>(null);
  const [q, setQ] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const op = useDraftDialog(() => setPreview(null));
  const parse = useMutation({
    mutationFn: () =>
      mode === "file"
        ? file
          ? uploadKnowledge(file)
          : Promise.reject(new Error("请选择文件。"))
        : apiRequest<KnowledgeDraft>("/knowledge/preview-text", {
            method: "POST",
            body: { title, text },
          }),
    onSuccess: setPreview,
  });
  const results = useQuery({
    queryKey: ["knowledge", searchTerm],
    queryFn: () =>
      apiRequest<KnowledgeResult[]>(
        "/knowledge/search?q=" + encodeURIComponent(searchTerm),
      ),
    enabled: searchTerm.length > 0,
  });
  return (
    <section>
      <PageHeading
        title="知识与学习"
        description="先解析、检查来源和切片，再确认导入。知识与个人记忆分开存储，不会成为系统指令。"
      />
      <div className="grid two">
        <article className="panel">
          <div className="section-top">
            <h2>导入资料</h2>
            <div className="actions">
              <button
                className={
                  "button small " + (mode === "text" ? "" : "secondary")
                }
                onClick={() => {
                  setMode("text");
                  setPreview(null);
                }}
              >
                粘贴文本
              </button>
              <button
                className={
                  "button small " + (mode === "file" ? "" : "secondary")
                }
                onClick={() => {
                  setMode("file");
                  setPreview(null);
                }}
              >
                上传文件
              </button>
            </div>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setPreview(null);
              parse.mutate();
            }}
          >
            {mode === "text" ? (
              <>
                <div className="field">
                  <label htmlFor="knowledge-title">知识标题</label>
                  <input
                    id="knowledge-title"
                    value={title}
                    maxLength={200}
                    required
                    onChange={(e) => setTitle(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="knowledge-text">知识正文</label>
                  <textarea
                    id="knowledge-text"
                    value={text}
                    required
                    style={{ minHeight: 220 }}
                    onChange={(e) => setText(e.target.value)}
                  />
                </div>
              </>
            ) : (
              <div className="field">
                <label htmlFor="knowledge-file">知识文件</label>
                <input
                  id="knowledge-file"
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                {file && (
                  <small>
                    {file.name} · {(file.size / 1024).toFixed(1)} KiB
                  </small>
                )}
              </div>
            )}
            <p className="muted">
              仅接受UTF-8文本与Markdown，单文件最多5
              MiB；不会按文件中的指令执行操作。
            </p>
            <ErrorMessage error={parse.error} />
            <button
              className="button"
              disabled={
                parse.isPending ||
                (mode === "text" ? !title.trim() || !text.trim() : !file)
              }
            >
              <Upload size={14} />
              {parse.isPending ? "正在上传与解析…" : "解析并生成预览"}
            </button>
          </form>
          {preview && (
            <section
              className="source-detail"
              role="region"
              aria-label="知识切片预览"
            >
              <h2>预览切片</h2>
              <p>
                {preview.preview.title} · {preview.preview.characters} 字符 ·
                接受 {preview.preview.accepted.length} 段 · 重复/拒绝{" "}
                {preview.preview.rejected.length} 段
              </p>
              <small>
                {preview.preview.semantic_status === "unconfigured"
                  ? "当前使用精确哈希与词面去重"
                  : preview.preview.semantic_status === "available"
                    ? "已使用配置的向量与词面去重"
                    : "向量服务不可用，已回退到词面去重"}
                ；向量去重每次最多处理 {preview.preview.semantic_chunk_limit}{" "}
                段。
              </small>
              <div className="file-preview">
                {preview.preview.accepted.map((c, i) => (
                  <article key={i}>
                    <small>切片 {i + 1}</small>
                    <p>{c.content}</p>
                  </article>
                ))}
              </div>
              {preview.preview.rejected.length > 0 && (
                <details>
                  <summary>查看重复与拒绝原因</summary>
                  <pre>{JSON.stringify(preview.preview.rejected, null, 2)}</pre>
                </details>
              )}
              <button
                className="button"
                style={{ marginTop: 15 }}
                onClick={() => op.openDraft(preview.draft)}
              >
                检查导入差异
              </button>
            </section>
          )}
          {op.success && (
            <p role="status" className="success-text">
              {op.success}
            </p>
          )}
        </article>
        <div>
          <article className="panel">
            <h2>已确认的知识来源</h2>
            <QueryState query={sources}>
              {sources.data?.length ? (
                <div>
                  {sources.data.map((s) => (
                    <div className="section-top" key={s.id}>
                      <div>
                        <FileText
                          size={14}
                          style={{ display: "inline", marginRight: 8 }}
                        />
                        <strong>
                          #{s.id} {s.title}
                        </strong>
                        <br />
                        <span className="timestamp">
                          {formatTime(s.created_at)}
                        </span>
                        <br />
                        <small>SHA256 {s.sha256.slice(0, 16)}…</small>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty">尚无已确认导入的知识。</p>
              )}
            </QueryState>
          </article>
          <article className="panel">
            <h2>检索已导入资料</h2>
            <form
              className="toolbar"
              onSubmit={(e) => {
                e.preventDefault();
                setSearchTerm(q.trim());
              }}
            >
              <div className="field" style={{ flex: 1, margin: 0 }}>
                <label htmlFor="knowledge-query">查询内容</label>
                <input
                  id="knowledge-query"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  maxLength={200}
                />
              </div>
              <button
                className="button secondary"
                disabled={!q.trim() || results.isFetching}
              >
                检索
              </button>
            </form>
            {searchTerm && (
              <QueryState query={results}>
                {results.data?.length ? (
                  results.data.map((r) => (
                    <article className="source-detail" key={r.id}>
                      <h3>
                        来源 #{r.source_id} · {r.title}
                      </h3>
                      <p className="source-quote">{r.content}</p>
                      <small>资料文本，仅供引用</small>
                    </article>
                  ))
                ) : (
                  <p className="empty">未找到匹配资料。</p>
                )}
              </QueryState>
            )}
          </article>
        </div>
      </div>
      {op.confirmation}
    </section>
  );
}
