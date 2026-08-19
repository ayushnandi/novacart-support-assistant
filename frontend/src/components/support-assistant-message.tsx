import { MarkdownText } from "@/components/markdown-text";
import { cn } from "@/lib/utils";
import {
  ActionBarPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { ThumbsDownIcon, ThumbsUpIcon, UserIcon } from "lucide-react";
import type { FC } from "react";

type SupportMetadata = {
  escalated?: boolean;
  humanOffered?: boolean;
  intent?: string | null;
};

const FEEDBACK_BUTTON_CLASS =
  "hover:text-foreground hover:bg-accent inline-flex size-7 items-center justify-center rounded-md transition-colors cursor-pointer disabled:pointer-events-none disabled:opacity-50";

export const SupportAssistantMessage: FC = () => {
  const custom = useAuiState(
    (s) => (s.message.metadata?.custom ?? {}) as SupportMetadata,
  );
  const isRunning = useAuiState((s) => s.message.status?.type === "running");
  // The runtime records this once feedback is submitted; reading it here is what gives
  // the buttons a visible selected state instead of looking like nothing happened.
  const submittedFeedback = useAuiState(
    (s) => s.message.metadata?.submittedFeedback?.type,
  );

  return (
    <MessagePrimitive.Root
      data-role="assistant"
      className="fade-in slide-in-from-bottom-1 animate-in relative mb-6 px-2 duration-150"
    >
      <div className="text-foreground leading-relaxed wrap-break-word">
        <MessagePrimitive.Parts components={{ Text: MarkdownText }} />
      </div>

      <MessagePrimitive.Error>
        <ErrorPrimitive.Root className="border-destructive bg-destructive/10 text-destructive mt-2 rounded-md border p-3 text-sm">
          <ErrorPrimitive.Message className="line-clamp-2" />
        </ErrorPrimitive.Root>
      </MessagePrimitive.Error>

      {!isRunning && custom.escalated && (
        <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <UserIcon className="size-3.5" />
          Handed to agent
        </div>
      )}

      {/* Retrieved FAQ sources are still returned by /chat and stored on every message
          row for the audit log - they're just noise in the chat bubble, since retrieval
          always returns the top 3 whether or not the answer actually used them. */}

      {!isRunning && (
        <ActionBarPrimitive.Root
          hideWhenRunning
          className="text-muted-foreground mt-1 flex items-center gap-1"
        >
          <ActionBarPrimitive.FeedbackPositive
            aria-label="Good response"
            title="Good response"
            className={cn(
              FEEDBACK_BUTTON_CLASS,
              submittedFeedback === "positive" && "text-green-600 dark:text-green-500",
            )}
          >
            <ThumbsUpIcon
              className={cn(
                "size-4",
                submittedFeedback === "positive" && "fill-current",
              )}
            />
          </ActionBarPrimitive.FeedbackPositive>

          <ActionBarPrimitive.FeedbackNegative
            aria-label="Bad response"
            title="Bad response"
            className={cn(
              FEEDBACK_BUTTON_CLASS,
              submittedFeedback === "negative" && "text-red-600 dark:text-red-500",
            )}
          >
            <ThumbsDownIcon
              className={cn(
                "size-4",
                submittedFeedback === "negative" && "fill-current",
              )}
            />
          </ActionBarPrimitive.FeedbackNegative>

          {submittedFeedback && (
            <span className="ml-1 text-xs">Thanks for the feedback</span>
          )}
        </ActionBarPrimitive.Root>
      )}
    </MessagePrimitive.Root>
  );
};
