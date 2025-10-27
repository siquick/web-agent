import { generateId } from "ai";
import { Loader2, RefreshCcw } from "lucide-react";
import { ChangeEvent, FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "../ui/button";
import { Card, CardContent } from "../ui/card";
import { ScrollArea } from "../ui/scroll-area";
import { Textarea } from "../ui/textarea";
import { ChatMessageBubble } from "./chat-message-bubble";
import type { ChatMessage, MessageMetadata } from "./types";

const DEFAULT_SYSTEM_PROMPT =
  "You are a helpful research assistant. Cite sources when possible. Respond using GitHub-flavored Markdown and prefer tables when comparing options.";
const DEFAULT_MODEL = "Qwen/Qwen3-32B:cerebras";
const TOOLTIP_LABEL = "Clear conversation";

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

export function ChatPanel() {
  const apiUrl = useMemo(
    () => (import.meta.env.VITE_WEB_AGENT_API_URL as string | undefined) ?? "http://127.0.0.1:8000",
    []
  );
  const model = useMemo(() => (import.meta.env.VITE_WEB_AGENT_MODEL as string | undefined) ?? DEFAULT_MODEL, []);
  const systemPrompt = useMemo(
    () => (import.meta.env.VITE_WEB_AGENT_SYSTEM_PROMPT as string | undefined) ?? DEFAULT_SYSTEM_PROMPT,
    []
  );

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: generateId(),
      role: "system",
      content: systemPrompt,
    },
  ]);
  const [{ isLoading, error }, setStatus] = useState<{
    isLoading: boolean;
    error: string | null;
  }>({
    isLoading: false,
    error: null,
  });
  const [input, setInput] = useState("");

  const scrollAreaRef = useRef<HTMLDivElement | null>(null);

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
          top: Math.max(offsetTop - 16, 0),
          behavior: "smooth",
        });
      }
    }
  }, [messages]);

  const visibleMessages = useMemo(
    () => messages.filter((message) => message.role !== "system") as ChatMessage[],
    [messages]
  );

  const callChatApi = useCallback(
    async (nextMessages: ChatMessage[]) => {
      setStatus({ isLoading: true, error: null });
      try {
        const response = await fetch(`${apiUrl}/v1/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model,
            stream: false,
            messages: formatMessagesForApi(nextMessages),
          }),
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

        const assistantEntry: ChatMessage = {
          id: generateId(),
          role: "assistant",
          content: text,
          metadata,
        };

        setMessages([...nextMessages, assistantEntry]);
        setStatus({ isLoading: false, error: null });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unexpected error while calling Web Agent API.";
        setStatus({ isLoading: false, error: message });
      }
    },
    [apiUrl, model, setMessages]
  );

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || isLoading) {
        return;
      }

      const userMessage: ChatMessage = {
        id: generateId(),
        role: "user",
        content: trimmed,
      };

      const nextMessages = [...messages, userMessage];
      setMessages(nextMessages);
      setInput("");
      await callChatApi(nextMessages);
    },
    [callChatApi, input, isLoading, messages]
  );

  const handleReset = useCallback(() => {
    setMessages([
      {
        id: generateId(),
        role: "system",
        content: systemPrompt,
      },
    ]);
    setStatus({ isLoading: false, error: null });
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

  return (
    <Card className="flex h-full flex-col overflow-hidden border-border/70 bg-card/80 shadow-lg">
      <CardContent className="flex h-full flex-col gap-6 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">Open Source Web Agent Assistant</h2>
            <p className="text-sm text-muted-foreground">Powered by {model}</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={handleReset}
            disabled={isLoading}
            title={TOOLTIP_LABEL}
            aria-label={TOOLTIP_LABEL}
          >
            <RefreshCcw className="h-4 w-4" />
          </Button>
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
              {isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Thinking…
                </div>
              ) : null}
            </div>
          </ScrollArea>
        </div>
        {error ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}
        <form onSubmit={handleSubmit} className="space-y-3">
          <Textarea
            placeholder="Ask the agent anything…"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <div className="flex justify-end">
            <Button type="submit" disabled={isLoading || !input.trim()}>
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Sending…
                </span>
              ) : (
                "Send"
              )}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
