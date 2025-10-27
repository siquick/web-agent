import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../../lib/utils";
import { Avatar } from "../ui/avatar";
import type { ChatMessage } from "./types";

const TOOL_SECTION_TITLE = "Tool usage";

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
  code: ({ node, inline, className, children = [], ...props }) => {
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

function renderToolMetadata(message: ChatMessage) {
  const metadata = message.metadata;
  if (!metadata) {
    return null;
  }

  const hasTools = metadata.tool_calls && metadata.tool_calls.length > 0;
  const hasReflections = metadata.reflections && metadata.reflections.length > 0;

  if (!hasTools && !hasReflections && !metadata.refined_query) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2 rounded-lg border border-border/70 bg-muted/40 p-3 text-sm text-muted-foreground">
      {metadata.refined_query ? (
        <p>
          <span className="font-medium text-foreground">Refined query:</span>{" "}
          {metadata.refined_query}
        </p>
      ) : null}
      {hasTools ? (
        <div className="space-y-2">
          <p className="font-medium text-foreground">{TOOL_SECTION_TITLE}</p>
          <ul className="space-y-1.5">
            {metadata.tool_calls.map((call, index) => (
              <li key={`${call.name}-${index}`} className="rounded-md bg-background/80 p-2">
                <p className="font-semibold text-foreground">{call.name}</p>
                <pre className="mt-1 overflow-x-auto rounded bg-muted/70 p-2 text-xs">
                  {JSON.stringify(call.arguments, null, 2)}
                </pre>
                {call.output_preview ? (
                  <p className="mt-1 text-xs italic leading-relaxed text-muted-foreground">
                    {call.output_preview}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
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
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={markdownComponents}
          className="markdown"
        >
          {message.content}
        </ReactMarkdown>
        {isAssistant ? renderToolMetadata(message) : null}
      </div>
      {isUser ? <Avatar fallback="You" className="bg-primary text-primary-foreground" /> : null}
    </div>
  );
}
