import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ChatResult } from '../../lib/types';
import { ChatTrace } from './ChatTrace';

const trace: ChatResult['trace'] = {
  decision: { strategy: 'answer', analysis_mode: 'llm', generation_mode: 'llm' },
  recalled_memories: [{ id: 7, content: '有来源的资料', status: 'active' }],
  knowledge_sources: [{ source_id: 4 }], guard: { guarded: true, route: 'boundary' },
  verifier: { available: false, reason: '尚未批准' }, tool_calls: [{ tool: 'lookup', status: 'success' }],
};
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('does no hidden serialization and reveals all original trace groups only when opened', async () => {
  const stringify = vi.spyOn(JSON, 'stringify');
  const view = render(<ChatTrace trace={trace} />);
  view.rerender(<ChatTrace trace={{ ...trace }} />);
  expect(stringify.mock.calls.filter(call => call[0] === trace.decision)).toHaveLength(0);
  expect(view.container.querySelectorAll('pre')).toHaveLength(0);
  fireEvent.click(screen.getByText('本轮决策与来源'));
  await waitFor(() => expect(view.container.querySelectorAll('pre')).toHaveLength(5));
  const values = [...view.container.querySelectorAll('pre')].map(pre => JSON.parse(pre.textContent!));
  expect(values).toEqual([trace.decision, trace.recalled_memories, trace.knowledge_sources,
    { guard: trace.guard, verifier: trace.verifier }, trace.tool_calls]);
  expect(screen.getByText('本轮由安全或现实边界规则直接回应。')).toBeInTheDocument();
  fireEvent.click(screen.getByText('本轮决策与来源'));
  await waitFor(() => expect(view.container.querySelectorAll('pre')).toHaveLength(0));
  stringify.mockClear(); view.rerender(<ChatTrace trace={trace} />);
  expect(stringify.mock.calls.filter(call => call[0] === trace.decision)).toHaveLength(0);
});
it('shows updated sources when reopened and does not retain the previous trace body', async () => {
  const view = render(<ChatTrace trace={trace} />);
  fireEvent.click(screen.getByText('本轮决策与来源'));
  await screen.findByText('有来源的资料', { exact: false });
  fireEvent.click(screen.getByText('本轮决策与来源'));
  await waitFor(() => expect(view.container.querySelectorAll('pre')).toHaveLength(0));
  const updated = { ...trace, recalled_memories: [], guard: { guarded: false, route: 'normal' }, decision: { strategy: 'new' } };
  view.rerender(<ChatTrace trace={updated} />);
  fireEvent.click(screen.getByText('本轮决策与来源'));
  await waitFor(() => expect(view.container.querySelectorAll('pre')).toHaveLength(5));
  expect(JSON.parse(view.container.querySelector('pre')!.textContent!)).toEqual(updated.decision);
  expect(screen.queryByText('有来源的资料', { exact: false })).not.toBeInTheDocument();
  expect(screen.queryByText('本轮由安全或现实边界规则直接回应。')).not.toBeInTheDocument();
});
