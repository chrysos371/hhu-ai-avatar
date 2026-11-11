import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LocalActionReceipts } from './LocalActionReceipts';

const read = vi.hoisted(() => vi.fn());
vi.mock('../../lib/actionReceipts', async importOriginal => ({ ...await importOriginal<object>(), readActionReceipts: read }));
const version = { instance_id: 'server', revision: 0 };
const item = { id: 1, source_message_id: 2, session_id: 'session', context_revision: 0,
  action: 'reminder.created', reminder_id: 3, recorded_at: 1700000000 };
const page = { ...version, items: [item], has_more: false, next_after_id: null,
  scope: 'current_visible_local_sql_receipts', notification_delivery_verified: false };

describe('actual local action records', () => {
  beforeEach(() => read.mockReset());
  it('reads only on explicit request and distinguishes claim from delivery', async () => {
    read.mockResolvedValue({ ...page, items: [{ ...item, action: 'reminder.claimed_due' }] });
    render(<LocalActionReceipts version={version} busy={false} />);
    expect(read).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '核验本地操作记录' }));
    expect(await screen.findByText(/记录到期提醒（送达未核验）/)).toBeVisible();
    expect(screen.getByText(/不代表当前提醒状态或通知已经送达/)).toBeVisible();
  });
  it('empty visible evidence never claims no historical action', async () => {
    read.mockResolvedValue({ ...page, items: [] });
    render(<LocalActionReceipts version={version} busy={false} />);
    fireEvent.click(screen.getByRole('button', { name: '核验本地操作记录' }));
    expect(await screen.findByText(/这不能证明此前没有操作/)).toBeVisible();
  });
  it('pages actual records without duplicate requests while loading', async () => {
    read.mockResolvedValueOnce({ ...page, has_more: true, next_after_id: 1 }).mockResolvedValueOnce({
      ...page, items: [{ ...item, id: 2, action: 'reminder.cancelled' }] });
    render(<LocalActionReceipts version={version} busy={false} />);
    fireEvent.click(screen.getByRole('button', { name: '核验本地操作记录' }));
    fireEvent.click(await screen.findByRole('button', { name: '加载更多操作记录' }));
    expect(await screen.findByText(/取消提醒/)).toBeVisible();
    expect(screen.getByText(/创建提醒/)).toBeVisible();
    expect(read.mock.calls[1][1]).toBe(1);
  });
  it('clears records on query failure', async () => {
    read.mockResolvedValueOnce(page).mockRejectedValueOnce(new Error('鉴权失败'));
    render(<LocalActionReceipts version={version} busy={false} />);
    fireEvent.click(screen.getByRole('button', { name: '核验本地操作记录' }));
    expect(await screen.findByText(/创建提醒/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '核验本地操作记录' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('鉴权失败');
    expect(screen.queryByText(/创建提醒/)).not.toBeInTheDocument();
  });
  it.each([{ instance_id: 'new-server', revision: 0 }, { instance_id: 'server', revision: 1 }])(
    'aborts and discards delayed old response when version becomes %j', async next => {
      let release!: (value: unknown) => void;
      read.mockImplementation(() => new Promise(resolve => { release = resolve; }));
      const { rerender } = render(<LocalActionReceipts version={version} busy={false} />);
      fireEvent.click(screen.getByRole('button', { name: '核验本地操作记录' }));
      const signal = read.mock.calls[0][2] as AbortSignal;
      rerender(<LocalActionReceipts version={next} busy={false} />);
      expect(signal.aborted).toBe(true);
      await act(async () => release(page));
      expect(screen.queryByText(/创建提醒/)).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: '核验本地操作记录' })).toBeEnabled();
    });
  it('clears already loaded evidence on privacy revision and disables writes while busy', async () => {
    read.mockResolvedValue(page);
    const { rerender } = render(<LocalActionReceipts version={version} busy={false} />);
    fireEvent.click(screen.getByRole('button', { name: '核验本地操作记录' }));
    await waitFor(() => expect(screen.getByText(/创建提醒/)).toBeVisible());
    rerender(<LocalActionReceipts version={{ ...version, revision: 1 }} busy />);
    expect(screen.queryByText(/创建提醒/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '核验本地操作记录' })).toBeDisabled();
  });
});
