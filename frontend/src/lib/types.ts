export type OperationType =
  | "persona.update"
  | "emotion.override"
  | "knowledge.import"
  | "memory.batch";
export interface Draft {
  draft_id: number;
  operation_type: OperationType;
  diff: { field: string; before: unknown; after: unknown }[];
  warnings: string[];
  expires_at: number;
  confirmation_token: string;
  proposal_provider?: "local" | "cloud";
}
export interface PersonaData {
  name: string;
  core_identity: string;
  expression_principles: string;
  relationship_boundaries: string;
  immutable_rules: string;
  temperature_bias: number;
  initiative: number;
}
export interface PersonaVersion {
  id: number;
  parent_id: number | null;
  data: PersonaData;
  created_at: number;
}
export interface MemoryRow {
  id: number;
  content: string;
  memory_type: string;
  status: string;
  created_at: number;
  predecessor_id?: number | null;
  strength?: number;
  confirmation_status?: string;
  sources?: {
    id: number;
    evidence: string | null;
    message_content: string | null;
    session_id: string | null;
    created_at: number;
  }[];
  tags?: string[];
}
export interface Reminder {
  id: number;
  title: string;
  due_at: number;
  created_at: number;
  status: string;
  notified_at: number | null;
}
export interface AuditEvent {
  id: number;
  draft_id: number;
  operation_type: OperationType;
  actor: string;
  status: "success" | "failed";
  before: unknown;
  after: unknown;
  created_at: number;
  error: string | null;
}
export interface ChatEvent {
  timestamp: number;
  strategy: string;
  route: string;
  valence: number;
  arousal: number;
}
export interface Dashboard {
  counts: Record<string, number>;
  persona_version: number;
  emotion: { valence: number; arousal: number; label: string };
  energy: number;
  verification_rate: number | null;
  verification_reason: string;
  recent_events: ChatEvent[];
  audit: AuditEvent[];
}
export interface SystemInfo {
  mode: string;
  backend: { available: boolean };
  model: { configured: boolean; available: boolean | null; reason: string };
  counts: Record<string, number>;
  legacy_writes_enabled: boolean;
}
export interface Health {
  name: string;
  configured: boolean;
  available: boolean | null;
  last_error: string | null;
}
export interface EmotionInfo {
  automatic: { valence: number; arousal: number };
  effective: { valence: number; arousal: number };
  user_observation: { valence: number; arousal: number };
  override: {
    id: number;
    data: { valence: number; arousal: number; reason: string };
    starts_at: number;
    expires_at: number;
  } | null;
  recent_observations: ChatEvent[];
}
export interface KnowledgeSource {
  id: number;
  title: string;
  sha256: string;
  created_at: number;
}
export interface KnowledgeResult {
  id: number;
  source_id: number;
  title: string;
  content: string;
  untrusted: true;
}
export interface KnowledgePreview {
  title: string;
  characters: number;
  accepted: { content: string; sha256: string }[];
  rejected: { sha256: string; reason: string }[];
  semantic_status: string;
  semantic_chunk_limit: number;
}
export interface KnowledgeDraft {
  preview: KnowledgePreview;
  draft: Draft;
}
export interface ChatResult {
  reply: string;
  emotion: string;
  strategy: string;
  trace: {
    model?: string | null;
    model_profile?: string;
    persona_version?: number | null;
    analysis_status?: string;
    reply_degraded?: boolean;
    protocol_fallbacks?: string[];
    total_ms?: number;
    recalled_memories: { id: number; content: string; status: string }[];
    knowledge_sources?: unknown[];
    decision: Record<string, unknown>;
    guard: {
      route: string;
      guarded: boolean;
      output_adjustment?: string | null;
    };
    verifier: { available: boolean; reason: string; delivery_check?: unknown };
    tool_calls: { tool: string; status: string }[];
  };
}
export interface Summary {
  items: { message_id: number; text: string; created_at: number }[];
  characters: number;
  max_characters: number;
}
