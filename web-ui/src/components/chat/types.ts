export interface ToolCallMetadata {
  name: string;
  arguments: Record<string, unknown>;
  output_preview?: string;
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
}

export type ChatRole = "system" | "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  metadata?: MessageMetadata;
};
