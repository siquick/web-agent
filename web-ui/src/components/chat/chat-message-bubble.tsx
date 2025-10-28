import { Loader2 } from "lucide-react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../../lib/utils";
import { Avatar } from "../ui/avatar";
import type { ChatMessage, LiveToolCall, MessageMetadata } from "./types";

const TOOL_SECTION_TITLE = "Tool activity";

const markdownComponents: Components = {
  p: ({ node, className, ...props }) => (
    <p className={cn("mb-3 text-sm leading-relaxed last:mb-0", className)} {...props} />
  ),
  h1: ({ node, className, ...props }) => (
    <h1 className={cn("mb-3 text-xl font-semibold", className)} {...props} />
  ),
  h2: ({ node, className, ...props }) => (
    <h2 className={cn("mb-3 text-lg font-semibold", className)} {...props} />
  ),
  h3: ({ node, className, ...props }) => (
    <h3 className={cn("mb-2 text-base font-semibold", className)} {...props} />
  ),
  a: ({ node, className, ...props }) => (
    <a
      className={cn("font-medium underline underline-offset-2 hover:opacity-80", className)}
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    />
  ),
  ul: ({ node, className, ...props }) => (
    <ul
      className={cn(
        "mb-3 ml-5 list-disc space-y-1.5 text-sm leading-relaxed",
        className,
      )}
      {...props}
    />
  ),
  ol: ({ node, className, ...props }) => (
    <ol
      className={cn(
        "mb-3 ml-5 list-decimal space-y-1.5 text-sm leading-relaxed",
        className,
      )}
      {...props}
    />
  ),
  li: ({ node, className, ...props }) => (
    <li className={cn("marker:text-current [&>p]:m-0", className)} {...props} />
  ),
  table: ({ node, className, children, ...props }) => (
    <div className="mb-3 overflow-x-auto rounded-lg border border-border/60">
      <table
        className={cn(
          "w-full min-w-[560px] border-collapse text-sm text-foreground [&_tbody_tr:nth-child(odd)]:bg-muted/60",
          className,
        )}
        {...props}
      >
        {children}
      </table>
    </div>
  ),
  thead: ({ node, className, ...props }) => (
    <thead className={cn("bg-muted/80 text-xs uppercase tracking-wide text-muted-foreground", className)} {...props} />
  ),
  tbody: ({ node, className, ...props }) => (
    <tbody className={cn("text-sm", className)} {...props} />
  ),
  tr: ({ node, className, ...props }) => (
    <tr className={cn("border-b border-border/80 last:border-b-0", className)} {...props} />
  ),
  th: ({ node, className, ...props }) => (
    <th
      className={cn(
        "whitespace-pre-wrap px-3 py-2 text-left font-semibold text-foreground",
        className,
      )}
      {...props}
    />
  ),
  td: ({ node, className, ...props }) => (
    <td
      className={cn(
        "whitespace-pre-wrap px-3 py-2 align-top text-sm text-foreground",
        className,
      )}
      {...props}
    />
  ),
  blockquote: ({ node, className, ...props }) => (
    <blockquote
      className={cn(
        "mb-3 border-l-2 border-border/70 pl-3 text-sm italic opacity-90",
        className,
      )}
      {...props}
    />
  ),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  code: ({ node, inline, className, children = [], ...props }: any) => {
    const inner = Array.isArray(children) ? children.join("") : String(children);

    if (inline) {
      return (
        <code
          className={cn("rounded bg-muted px-1.5 py-0.5 font-mono text-xs", className)}
          {...props}
        >
          {inner}
        </code>
      );
    }

    return (
      <pre className="mb-3 overflow-x-auto rounded-lg bg-muted p-3 text-xs">
        <code className={cn("font-mono", className)} {...props}>
          {inner}
        </code>
      </pre>
    );
  },
};

interface ChatMessageBubbleProps {
  message: ChatMessage;
}

function renderThinkingContent(message: ChatMessage) {
  const thinking = message.thinking?.trim();
  if (!thinking) {
    return null;
  }

  return (
    <details
      className="mt-3 space-y-2 rounded-lg border border-border/70 bg-muted/30 p-3 text-xs leading-relaxed text-muted-foreground"
      open={message.streaming ?? false}
    >
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-foreground/70">
        Thinking
      </summary>
      <pre className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{thinking}</pre>
    </details>
  );
}

function renderLiveToolCalls(calls?: LiveToolCall[], refinedQuery?: string | null) {
  if (!calls || calls.length === 0) {
    if (!refinedQuery) {
      return null;
    }
    calls = [];
  }

  return (
    <div className="mt-3 space-y-2 rounded-lg border border-border/70 bg-muted/40 p-3 text-xs text-muted-foreground">
      <p className="font-medium text-foreground">{TOOL_SECTION_TITLE}</p>
      {refinedQuery ? (
        <p className="rounded-md bg-background/70 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
          <span className="font-semibold text-foreground">Refined query:</span>{" "}
          {refinedQuery}
        </p>
      ) : null}
      {calls.length ? (
        <ul className="space-y-1">
          {calls.map((call) => (
            <li key={call.id} className="flex items-center justify-between rounded-md bg-background/70 px-3 py-2">
              <span className="font-semibold text-foreground">{call.name}</span>
              <span
                className={cn(
                  "text-[11px] font-medium uppercase tracking-wide",
                  call.status === "running" ? "text-amber-600" : "text-emerald-600",
                )}
              >
                {call.status === "running" ? "Running" : "Completed"}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function renderFinalMetadata(metadata?: MessageMetadata) {
  if (!metadata) {
    return null;
  }

  const hasReflections = metadata.reflections && metadata.reflections.length > 0;

  if (!hasReflections) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2 rounded-lg border border-border/70 bg-muted/40 p-3 text-sm text-muted-foreground">
      {hasReflections ? (
        <div className="space-y-2">
          <p className="font-medium text-foreground">Reflections</p>
          <ul className="space-y-1">
            {metadata.reflections.map((reflection, index) => (
              <li key={index}>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  <span className="font-semibold text-foreground">
                    Needs more context?{" "}
                  </span>
                  {reflection.requires_more_context ? "Yes" : "No"}
                </p>
                {reflection.reason ? (
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    <span className="font-semibold text-foreground">Reason:</span>{" "}
                    {reflection.reason}
                  </p>
                ) : null}
                {reflection.follow_up_instruction ? (
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    <span className="font-semibold text-foreground">Instruction:</span>{" "}
                    {reflection.follow_up_instruction}
                  </p>
                ) : null}
                {reflection.suggested_query ? (
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    <span className="font-semibold text-foreground">Suggested query:</span>{" "}
                    {reflection.suggested_query}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isAssistant = message.role === "assistant";
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  if (isSystem) {
    return null;
  }

  return (
    <div
      className={cn(
        "flex w-full gap-3",
        isAssistant ? "items-start" : "items-end justify-end",
      )}
    >
      {isAssistant ? <Avatar fallback="AI" /> : null}
      <div
      className={cn(
        "max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm sm:max-w-[75%]",
        isAssistant
          ? "bg-card text-card-foreground"
          : "bg-primary text-primary-foreground",
      )}
    >
      {isAssistant ? (
        <>
          {renderThinkingContent(message)}
          {renderLiveToolCalls(message.liveToolCalls, message.metadata?.refined_query ?? null)}
        </>
      ) : null}
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
        className="markdown"
      >
        {message.content}
      </ReactMarkdown>
      {message.error ? (
        <div className="mt-3 rounded-lg border border-destructive/60 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {message.error}
        </div>
      ) : null}
      {isAssistant ? (
        <>
          {message.streaming ? (
            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Generating…
            </div>
          ) : null}
          {renderFinalMetadata(message.metadata)}
        </>
      ) : null}
    </div>
      {isUser ? <Avatar fallback="You" className="bg-primary text-primary-foreground" /> : null}
    </div>
  );
}
