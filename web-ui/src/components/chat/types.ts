export interface ToolCallMetadata {
  name: string;
  arguments: Record<string, unknown>;
  output_preview?: string;
}

export interface LiveToolCall {
  id: string;
  name: string;
  status: "running" | "completed";
  arguments: Record<string, unknown>;
  output?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface ReflectionMetadata {
  requires_more_context: boolean;
  reason?: string;
  follow_up_instruction?: string;
  suggested_query?: string;
}

export interface MessageMetadata {
  refined_query?: string | null;
  tool_calls: ToolCallMetadata[];
  reflections: ReflectionMetadata[];
  provider?: ProviderInfo;
}

export type ChatRole = "system" | "user" | "assistant";

export interface ProviderInfo {
  id: string;
  label: string;
  baseUrl?: string;
}

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  metadata?: MessageMetadata;
  thinking?: string;
  streaming?: boolean;
  liveToolCalls?: LiveToolCall[];
  error?: string;
  provider?: ProviderInfo;
  stopped?: boolean;
};

export interface ModelOption {
  id: string;
  displayName: string;
  description?: string;
  providerLabel?: string;
  providerId?: string;
  supportsStreaming: boolean;
}
