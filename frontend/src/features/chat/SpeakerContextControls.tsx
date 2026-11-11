import type { SpeakerChoice, SpeakerSnapshot } from '../../lib/speakerContext';

const labels = { current_user: '本人模式', fictional_character: '角色模式', unverified: '需确认说话者' };

export function SpeakerContextControls({ context, loading, error, disabled, switching, onChoice }: {
  context: SpeakerSnapshot | null; loading: boolean; error: Error | null; disabled: boolean;
  switching: SpeakerChoice | null; onChoice: (choice: SpeakerChoice) => void;
}) {
  const title = switching ? '正在确认选择…' : context ? labels[context.scope] : loading ? '正在核验语境…' : '语境待确认';
  const description = context?.scope === 'fictional_character'
    ? '角色对话不更新你的个人资料，也不执行提醒或联网操作。'
    : context?.scope === 'current_user'
      ? '新消息按你本人理解；真实操作仍需要独立、明确的请求。'
      : '选择本人或角色，核验后显示有效语境。切换不会发送输入框里的草稿。';
  return <div className="panel" data-speaker-context={switching ? 'pending' : context?.scope ?? 'unconfirmed'} aria-label="说话者语境">
    <div className="section-top"><h2>说话者语境</h2><span>{title}</span></div>
    <p className="muted">{description}</p>
    {error && <p className="notice">暂时无法核验语境，请刷新对话记录或重新选择说话者。</p>}
    <div className="section-top" style={{ marginBottom: 0 }}>
      <button type="button" className="button secondary" disabled={disabled || context?.scope === 'current_user'}
        onClick={() => onChoice('current_user')}>以本人说话</button>
      <button type="button" className="button secondary" disabled={disabled || context?.scope === 'fictional_character'}
        onClick={() => onChoice('fictional_character')}>进入角色</button>
    </div>
  </div>;
}
