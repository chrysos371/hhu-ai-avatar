import type { ChatResult } from './types';

export interface ConversationItem {
  id: number; role: 'user' | 'assistant'; text: string; session_id: string; created_at: number;
  redacted: boolean; result?: ChatResult;
}
export interface ConversationSnapshot {
  instance_id: string; revision: number; items: ConversationItem[];
  has_more: boolean; next_before_id: number | null;
}
export type ChatRow = Pick<ConversationItem, 'role' | 'text' | 'result'> & Partial<Omit<ConversationItem, 'role' | 'text' | 'result'>> & {
  pending?: boolean; cancelled?: boolean;
};
const eventName = 'avatar:conversation-privacy';
const channelName = 'avatar-conversation-privacy-v1';
const sender = crypto.randomUUID();

export function notifyConversationPrivacyChanged() {
  window.dispatchEvent(new Event(eventName));
  if (typeof window.BroadcastChannel === 'function') {
    const channel = new window.BroadcastChannel(channelName);
    channel.postMessage({ type: 'invalidate', sender });
    channel.close();
  }
}
export function subscribeConversationPrivacy(listener: () => void) {
  window.addEventListener(eventName, listener);
  const channel = typeof window.BroadcastChannel === 'function' ? new window.BroadcastChannel(channelName) : null;
  if (channel) channel.onmessage = event => {
    if (event.data?.type === 'invalidate' && event.data.sender !== sender) listener();
  };
  return () => { window.removeEventListener(eventName, listener); channel?.close(); };
}
