import { useEffect, useRef, useState } from 'react';
import { formatTime } from '../../lib/api';
import { localActionLabels, readActionReceipts, type ActionReceiptPage, type ActionReceiptVersion } from '../../lib/actionReceipts';

export function LocalActionReceipts({ version, busy }: { version: ActionReceiptVersion; busy: boolean }) {
  return <ReceiptPanel key={version.instance_id + ':' + version.revision} version={version} busy={busy} />;
}

function ReceiptPanel({ version, busy }: { version: ActionReceiptVersion; busy: boolean }) {
  const [page, setPage] = useState<ActionReceiptPage | null>(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState<string | null>(null);
  const mounted = useRef(false), active = useRef<AbortController | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; active.current?.abort(); }; }, []);
  async function load(more: boolean) {
    if (active.current || busy) return;
    const controller = new AbortController(); active.current = controller;
    setLoading(true); setError(null);
    try {
      const next = await readActionReceipts(version, more && page ? page.next_after_id ?? 0 : 0, controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      setPage(previous => ({ ...next, items: more && previous ? [...previous.items, ...next.items] : next.items }));
    } catch (cause) {
      if (!mounted.current || controller.signal.aborted) return;
      setPage(null); setError(cause instanceof Error ? cause.message : '操作记录暂时无法读取。');
    } finally {
      if (active.current === controller) active.current = null;
      if (mounted.current) setLoading(false);
    }
  }
  return <section className="panel" aria-label="实际本地操作">
    <h2>实际本地操作</h2>
    <p className="muted">按需查看已提交的本地记录。停止回复不会撤销此前已提交的操作。</p>
    <button type="button" className="button secondary" disabled={busy || loading} onClick={() => void load(false)}>
      {loading ? '正在核验操作记录…' : '核验本地操作记录'}</button>
    {error && <p role="alert">{error}</p>}
    {page && <>
      {!page.items.length && <p>当前没有可见的本地操作回执；这不能证明此前没有操作。</p>}
      {page.items.length > 0 && <ul>{page.items.map(item => <li key={item.id}>
        {localActionLabels[item.action]} · 提醒 #{item.reminder_id} · {formatTime(item.recorded_at)}
      </li>)}</ul>}
      {page.has_more && <button type="button" className="button secondary" disabled={busy || loading} onClick={() => void load(true)}>加载更多操作记录</button>}
      <p className="muted">回执记录本地提交，不代表当前提醒状态或通知已经送达。可在记忆页查看当前提醒。</p>
    </>}
  </section>;
}
