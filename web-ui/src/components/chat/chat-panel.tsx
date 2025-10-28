import { generateId } from "ai";
import { Loader2, RefreshCcw } from "lucide-react";
import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "../ui/button";
import { Card, CardContent } from "../ui/card";
import { ScrollArea } from "../ui/scroll-area";
import { Textarea } from "../ui/textarea";
import { ChatMessageBubble } from "./chat-message-bubble";
import type { ChatMessage, LiveToolCall, MessageMetadata, ModelOption } from "./types";

const DEFAULT_SYSTEM_PROMPT =
  "You are a helpful research assistant. Cite sources when possible. Respond using GitHub-flavored Markdown and prefer tables when comparing options.";
const MODEL_STORAGE_KEY = "web-agent:selected-model";

type ServerEvent = Record<string, unknown> & { type?: string };

function parseAssistantContent(data: unknown): string {
  if (!data) {
    return "";
  }
  if (typeof data === "string") {
    return data;
  }
  if (Array.isArray(data)) {
    return data
      .flatMap((node) => {
        if (typeof node === "string") {
          return node;
        }
        if (node && typeof node === "object" && "text" in node && typeof node.text === "string") {
          return node.text;
        }
        return [];
      })
      .join("")
      .trim();
  }
  return "";
}

function extractMetadata(payload: unknown): MessageMetadata | undefined {
  if (!payload || typeof payload !== "object") {
    return undefined;
  }

  const maybeMetadata = (payload as Record<string, unknown>).metadata;
  if (!maybeMetadata || typeof maybeMetadata !== "object") {
    return undefined;
  }

  const metadata = maybeMetadata as Record<string, unknown>;
  return {
    refined_query: typeof metadata.refined_query === "string" ? metadata.refined_query : null,
    tool_calls: Array.isArray(metadata.tool_calls)
      ? metadata.tool_calls
          .filter((candidate): candidate is Record<string, unknown> & { name: string } => {
            return Boolean(candidate && typeof candidate === "object" && "name" in candidate);
          })
          .map((call) => ({
            name: String(call.name),
            arguments: (call.arguments && typeof call.arguments === "object"
              ? (call.arguments as Record<string, unknown>)
              : {}) as Record<string, unknown>,
            output_preview:
              call.output_preview && typeof call.output_preview === "string" ? call.output_preview : undefined,
          }))
      : [],
    reflections: Array.isArray(metadata.reflections)
      ? metadata.reflections
          .filter((candidate) => Boolean(candidate && typeof candidate === "object"))
          .map((reflection) => {
            const record = reflection as Record<string, unknown>;
            return {
              requires_more_context: Boolean(record.requires_more_context),
              reason: typeof record.reason === "string" ? record.reason : undefined,
              follow_up_instruction:
                typeof record.follow_up_instruction === "string" ? record.follow_up_instruction : undefined,
              suggested_query: typeof record.suggested_query === "string" ? record.suggested_query : undefined,
            };
          })
      : [],
  };
}

function formatMessagesForApi(messages: ChatMessage[]) {
  return messages.map((message) => ({
    role: message.role,
    content: message.content,
  }));
}

function splitThinkingSegments(text: string): { thinking: string; visible: string } {
  const thinkingPattern = /<(?:thinking|think)>([\s\S]*?)<\/(?:thinking|think)>/i;
  const match = thinkingPattern.exec(text);
  if (!match) {
    return { thinking: "", visible: text };
  }
  const before = text.slice(0, match.index ?? 0);
  const after = text.slice((match.index ?? 0) + match[0].length);
  const visible = `${before}${after}`.replace(/^\s+/, "");
  return {
    thinking: match[1].trim(),
    visible: visible || "",
  };
}

function normalizeArguments(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // ignore
    }
  }
  return {};
}

function normalizeOutput(value: unknown): string | undefined {
  if (value == null) {
    return undefined;
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export function ChatPanel() {
  const apiUrl = useMemo(
    () => (import.meta.env.VITE_WEB_AGENT_API_URL as string | undefined) ?? "http://127.0.0.1:8000",
    []
  );

  const defaultModelFromEnv = useMemo(() => {
    const raw = import.meta.env.VITE_WEB_AGENT_MODEL as string | undefined;
    return raw?.trim() ? raw.trim() : null;
  }, []);
  const systemPrompt = useMemo(
    () => (import.meta.env.VITE_WEB_AGENT_SYSTEM_PROMPT as string | undefined) ?? DEFAULT_SYSTEM_PROMPT,
    []
  );

  const [models, setModels] = useState<ModelOption[]>([]);
  const [modelsStatus, setModelsStatus] = useState<{ isLoading: boolean; error: string | null }>({
    isLoading: true,
    error: null,
  });
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: generateId(),
      role: "system",
      content: systemPrompt,
    },
  ]);
  const [status, setStatus] = useState<{ isStreaming: boolean; error: string | null }>({
    isStreaming: false,
    error: null,
  });
  const [input, setInput] = useState("");

  const scrollAreaRef = useRef<HTMLDivElement | null>(null);
  const assistantBufferRef = useRef<{ id: string | null; text: string }>({ id: null, text: "" });
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!scrollAreaRef.current) {
      return;
    }
    const scrollContainer = scrollAreaRef.current.querySelector("[data-chat-scroll-container]");
    if (scrollContainer instanceof HTMLElement) {
      const lastAssistant = scrollContainer.querySelector("[data-last-assistant='true']");
      if (lastAssistant instanceof HTMLElement) {
        const offsetTop = lastAssistant.offsetTop;
        scrollContainer.scrollTo({
          top: Math.max(offsetTop - 24, 0),
          behavior: "smooth",
        });
      }
    }
  }, [messages]);

  useEffect(() => {
    let cancelled = false;
    async function loadModels() {
      setModelsStatus({ isLoading: true, error: null });
      try {
        const response = await fetch(`${apiUrl}/v1/models`);
        if (!response.ok) {
          throw new Error(response.statusText || "Failed to load models.");
        }
        const payload = (await response.json()) as { data?: unknown[] };
        const data = Array.isArray(payload?.data) ? payload.data : [];
        const mapped = data.map((entry) => {
          const record = entry as Record<string, unknown>;
          const metadata = normalizeArguments(record.metadata);
          const provider = normalizeArguments(metadata.provider);
          return {
            id: String(record.id),
            displayName:
              typeof metadata.display_name === "string" ? metadata.display_name : String(record.id ?? "model"),
            description: typeof metadata.description === "string" ? metadata.description : undefined,
            providerLabel:
              typeof provider.label === "string"
                ? provider.label
                : typeof record.owned_by === "string"
                  ? record.owned_by
                  : undefined,
            providerId: typeof provider.id === "string" ? provider.id : undefined,
            supportsStreaming: metadata.supports_streaming !== false,
          } satisfies ModelOption;
        });
        if (cancelled) {
          return;
        }
        setModels(mapped);
        setModelsStatus({ isLoading: false, error: null });
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : "Failed to load models.";
        setModels([]);
        setModelsStatus({ isLoading: false, error: message });
      }
    }

    void loadModels();
    return () => {
      cancelled = true;
    };
  }, [apiUrl]);

  useEffect(() => {
    if (!models.length) {
      return;
    }
    setSelectedModel((current) => {
      if (current && models.some((model) => model.id === current)) {
        return current;
      }
      let stored: string | null = null;
      if (typeof window !== "undefined") {
        stored = window.localStorage.getItem(MODEL_STORAGE_KEY);
      }
      if (stored && models.some((model) => model.id === stored)) {
        return stored;
      }
      if (defaultModelFromEnv && models.some((model) => model.id === defaultModelFromEnv)) {
        return defaultModelFromEnv;
      }
      return models[0]?.id ?? null;
    });
  }, [models, defaultModelFromEnv]);

  useEffect(() => {
    if (!selectedModel || typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(MODEL_STORAGE_KEY, selectedModel);
  }, [selectedModel]);

  const visibleMessages = useMemo(
    () => messages.filter((message) => message.role !== "system") as ChatMessage[],
    [messages]
  );

  const activeModel = useMemo(
    () => (selectedModel ? models.find((model) => model.id === selectedModel) ?? null : null),
    [models, selectedModel]
  );
  const canStream = activeModel?.supportsStreaming ?? true;

  const updateAssistantMessage = useCallback(
    (assistantId: string, updater: (message: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        let modified = false;
        const next = prev.map((message) => {
          if (message.id !== assistantId) {
            return message;
          }
          modified = true;
          return updater(message);
        });
        return modified ? next : prev;
      });
    },
    []
  );

  const handleServerEvent = useCallback(
    (event: ServerEvent, assistantId: string): boolean => {
      const type = typeof event.type === "string" ? event.type : "";

      if (type === "tool_call") {
        const status = typeof event.status === "string" ? event.status : "start";
        const callId = String(event.call_id ?? event.id ?? generateId());
        const name = typeof event.name === "string" ? event.name : "tool";
        const argumentsPayload = normalizeArguments(event.arguments);

        if (status === "start") {
          const liveCall: LiveToolCall = {
            id: callId,
            name,
            status: "running",
            arguments: argumentsPayload,
          };
          updateAssistantMessage(assistantId, (message) => {
            const existing: LiveToolCall[] = message.liveToolCalls ?? [];
            const without: LiveToolCall[] = existing.filter((call) => call.id !== callId);
            return {
              ...message,
              liveToolCalls: [...without, liveCall],
            };
          });
        } else {
          const output = normalizeOutput(event.output);
          updateAssistantMessage(assistantId, (message) => {
            const existing: LiveToolCall[] = message.liveToolCalls ?? [];
            const updated: LiveToolCall[] = existing.map((call) =>
              call.id === callId ? { ...call, status: "completed", output } : call
            );
            return {
              ...message,
              liveToolCalls: updated,
            };
          });
        }
        return false;
      }

      if (type === "answer") {
        const statusValue = typeof event.status === "string" ? event.status : "final";
        if (statusValue === "stream") {
          const chunk = typeof event.text === "string" ? event.text : "";
          assistantBufferRef.current.text += chunk;
          const { thinking, visible } = splitThinkingSegments(assistantBufferRef.current.text);
          updateAssistantMessage(assistantId, (message) => ({
            ...message,
            content: visible,
            thinking,
            streaming: true,
          }));
          return false;
        }

        const finalText =
          typeof event.text === "string" && event.text.trim().length
            ? event.text
            : assistantBufferRef.current.text;
        assistantBufferRef.current.text = finalText;
        const { thinking, visible } = splitThinkingSegments(finalText);
        updateAssistantMessage(assistantId, (message) => ({
          ...message,
          content: visible,
          thinking,
          metadata:
            (event.metadata && typeof event.metadata === "object"
              ? (event.metadata as MessageMetadata)
              : message.metadata) ?? message.metadata,
          streaming: false,
        }));
        return false;
      }

      if (type === "final_response") {
        const response = normalizeArguments(event.response);
        const choices = Array.isArray(response.choices) ? response.choices : [];
        const firstChoice = choices[0] as Record<string, unknown> | undefined;
        const assistantMessage = firstChoice?.message as Record<string, unknown> | undefined;
        if (assistantMessage) {
          const text = parseAssistantContent(assistantMessage.content);
          if (text) {
            assistantBufferRef.current.text = text;
            const { thinking, visible } = splitThinkingSegments(text);
            const metadata = extractMetadata(assistantMessage);
            updateAssistantMessage(assistantId, (message) => ({
              ...message,
              content: visible,
              thinking,
              metadata: metadata ?? message.metadata,
              streaming: false,
            }));
          } else {
            const metadata = extractMetadata(assistantMessage);
            if (metadata) {
              updateAssistantMessage(assistantId, (message) => ({
                ...message,
                metadata,
              }));
            }
          }
        }
        return false;
      }

      if (type === "error") {
        const message = typeof event.message === "string" ? event.message : "Agent failed to generate a response.";
        setStatus({ isStreaming: false, error: message });
        updateAssistantMessage(assistantId, (current) => ({
          ...current,
          streaming: false,
          error: message,
        }));
        return true;
      }

      if (type === "done") {
        return true;
      }

      return false;
    },
    [updateAssistantMessage]
  );

  const streamChat = useCallback(
    async (history: ChatMessage[], assistantId: string) => {
      let encounteredError = false;
      const controller = new AbortController();
      abortControllerRef.current = controller;
      assistantBufferRef.current = { id: assistantId, text: "" };

      try {
        const response = await fetch(`${apiUrl}/v1/chat/completions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: selectedModel,
            stream: true,
            messages: formatMessagesForApi(history),
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          const detail = typeof body.detail === "string" ? body.detail : response.statusText;
          throw new Error(detail || "Failed to reach Web Agent API.");
        }
        if (!response.body) {
          throw new Error("Streaming is not supported by the server response.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        let done = false;

        while (!done) {
          const { value, done: readerDone } = await reader.read();
          if (readerDone) {
            done = true;
          }
          if (value) {
            buffer += decoder.decode(value, { stream: !readerDone });
          }

          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const chunk = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);

            const dataLines = chunk
              .split("\n")
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trim());

            if (dataLines.length) {
              const payloadString = dataLines.join("");
              if (payloadString && payloadString !== "[DONE]") {
                try {
                  const parsed = JSON.parse(payloadString) as ServerEvent;
                  const shouldStop = handleServerEvent(parsed, assistantId);
                  if (shouldStop) {
                    done = true;
                    break;
                  }
                } catch {
                  // ignore malformed events
                }
              }
            }

            boundary = buffer.indexOf("\n\n");
          }
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        encounteredError = true;
        const message = error instanceof Error ? error.message : "Unexpected error while calling Web Agent API.";
        setStatus({ isStreaming: false, error: message });
        updateAssistantMessage(assistantId, (current) => ({
          ...current,
          streaming: false,
          error: message,
        }));
      } finally {
        abortControllerRef.current = null;
        assistantBufferRef.current = { id: null, text: "" };
        if (!encounteredError) {
          setStatus((prev) => (prev.isStreaming ? { ...prev, isStreaming: false } : prev));
          updateAssistantMessage(assistantId, (current) =>
            current.streaming ? { ...current, streaming: false } : current
          );
        }
      }
    },
    [apiUrl, handleServerEvent, selectedModel, updateAssistantMessage]
  );

  const sendNonStreaming = useCallback(
    async (history: ChatMessage[], assistantId: string) => {
      let encounteredError = false;
      const controller = new AbortController();
      abortControllerRef.current = controller;
      try {
        const response = await fetch(`${apiUrl}/v1/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: selectedModel,
            stream: false,
            messages: formatMessagesForApi(history),
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          const detail = typeof body.detail === "string" ? body.detail : response.statusText;
          throw new Error(detail || "Failed to reach Web Agent API.");
        }

        const payload = (await response.json()) as {
          choices?: Array<{
            message?: {
              content?: unknown;
              metadata?: unknown;
            };
          }>;
        };

        const choice = payload.choices?.[0];
        const assistantMessage = choice?.message;
        const text = parseAssistantContent(assistantMessage?.content) || "[no content]";
        const metadata = extractMetadata(assistantMessage);
        const { thinking, visible } = splitThinkingSegments(text);

        updateAssistantMessage(assistantId, (current) => ({
          ...current,
          content: visible,
          thinking,
          metadata,
          streaming: false,
        }));
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        encounteredError = true;
        const message = error instanceof Error ? error.message : "Unexpected error while calling Web Agent API.";
        setStatus({ isStreaming: false, error: message });
        updateAssistantMessage(assistantId, (current) => ({
          ...current,
          streaming: false,
          error: message,
        }));
      } finally {
        abortControllerRef.current = null;
        if (!encounteredError) {
          setStatus((prev) => (prev.isStreaming ? { ...prev, isStreaming: false } : prev));
        }
      }
    },
    [apiUrl, selectedModel, updateAssistantMessage]
  );

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || status.isStreaming) {
        return;
      }
      if (!selectedModel) {
        setStatus({ isStreaming: false, error: "Select a model before starting a conversation." });
        return;
      }

      const userMessage: ChatMessage = {
        id: generateId(),
        role: "user",
        content: trimmed,
      };

      const conversationForApi = [...messages, userMessage];
      const assistantId = generateId();
      const assistantPlaceholder: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
        liveToolCalls: [],
      };

      setMessages([...conversationForApi, assistantPlaceholder]);
      setInput("");
      setStatus({ isStreaming: true, error: null });

      if (canStream) {
        await streamChat(conversationForApi, assistantId);
      } else {
        await sendNonStreaming(conversationForApi, assistantId);
      }
    },
    [input, status.isStreaming, selectedModel, messages, canStream, streamChat, sendNonStreaming]
  );

  const handleReset = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    assistantBufferRef.current = { id: null, text: "" };
    setMessages([
      {
        id: generateId(),
        role: "system",
        content: systemPrompt,
      },
    ]);
    setStatus({ isStreaming: false, error: null });
    setInput("");
  }, [systemPrompt]);

  const handleInputChange = useCallback((event: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
  }, []);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void handleSubmit(event as unknown as FormEvent<HTMLFormElement>);
      }
    },
    [handleSubmit]
  );

  const handleModelChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    setSelectedModel(event.target.value || null);
  }, []);

  const handleStop = useCallback(() => {
    const controller = abortControllerRef.current;
    if (!controller) {
      return;
    }
    controller.abort();
    abortControllerRef.current = null;
    setStatus((prev) => ({ ...prev, isStreaming: false }));
    const assistantId = assistantBufferRef.current.id;
    if (assistantId) {
      updateAssistantMessage(assistantId, (message) => ({
        ...message,
        streaming: false,
      }));
    }
    assistantBufferRef.current = { id: null, text: assistantBufferRef.current.text };
  }, [updateAssistantMessage]);

  return (
    <Card className="flex h-full flex-col overflow-hidden border-border/70 bg-card/80 shadow-lg">
      <CardContent className="flex h-full flex-col gap-6 p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">Open Source Web Agent Assistant</h2>
            <p className="text-sm text-muted-foreground">
              Powered by{" "}
              {activeModel
                ? `${activeModel.displayName}${activeModel.providerLabel ? ` · ${activeModel.providerLabel}` : ""}`
                : "—"}
            </p>
          </div>
          <div className="flex flex-col items-start gap-2 sm:items-end">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Model
              </label>
              <select
                className="rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                value={selectedModel ?? ""}
                onChange={handleModelChange}
                disabled={modelsStatus.isLoading || status.isStreaming || models.length === 0}
              >
                {modelsStatus.isLoading ? (
                  <option value="">Loading models…</option>
                ) : models.length > 0 ? (
                  models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.displayName}
                      {model.providerLabel ? ` • ${model.providerLabel}` : ""}
                    </option>
                  ))
                ) : (
                  <option value="">No models available</option>
                )}
              </select>
            </div>
            {modelsStatus.error ? (
              <p className="max-w-xs text-right text-xs text-destructive">{modelsStatus.error}</p>
            ) : null}
            {!canStream ? (
              <p className="text-xs text-amber-600">
                Streaming disabled for this model. Responses will appear once complete.
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex-1">
          <ScrollArea className="h-full" ref={scrollAreaRef}>
            <div className="flex flex-col gap-4 pr-2" data-chat-scroll-container>
              {visibleMessages.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border/80 bg-muted/50 p-6 text-center text-sm text-muted-foreground">
                  Start the conversation by asking a question. The assistant can search, run tools, and return cited
                  answers.
                </div>
              ) : (
                visibleMessages.map((message, index) => {
                  const isLastAssistant = index === visibleMessages.length - 1 && message.role === "assistant";
                  return (
                    <div key={message.id} data-last-assistant={isLastAssistant ? "true" : undefined}>
                      <ChatMessageBubble message={message} />
                    </div>
                  );
                })
              )}
            </div>
          </ScrollArea>
        </div>
        {status.error ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {status.error}
          </div>
        ) : null}
        <form onSubmit={handleSubmit} className="space-y-3">
          <Textarea
            placeholder={selectedModel ? "Ask the agent anything…" : "Select a model to start chatting."}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={status.isStreaming || !selectedModel}
            rows={3}
          />
          <div className="flex items-center justify-between">
            {status.isStreaming ? (
              <Button type="button" variant="outline" onClick={handleStop}>
                Stop
              </Button>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-2">
              <Button type="submit" disabled={status.isStreaming || !input.trim() || !selectedModel}>
                {status.isStreaming ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Streaming…
                  </span>
                ) : (
                  "Send"
                )}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={handleReset}
                disabled={status.isStreaming}
                title="Clear conversation"
                aria-label="Clear conversation"
              >
                <RefreshCcw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );

}
