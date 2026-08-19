import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { CheckIcon, CopyIcon } from "lucide-react";
import { type FC, useState } from "react";

export const SessionBadge: FC<{ sessionId: string | null }> = ({ sessionId }) => {
  const [copied, setCopied] = useState(false);

  if (!sessionId) return null;

  const short = `${sessionId.slice(0, 8)}…`;

  const copy = async () => {
    await navigator.clipboard.writeText(sessionId);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      className="text-muted-foreground flex items-center gap-1 text-xs"
      title={sessionId}
    >
      <span className="font-mono">session: {short}</span>
      <TooltipIconButton
        tooltip={copied ? "Copied!" : "Copy session id"}
        size="icon-sm"
        onClick={copy}
      >
        {copied ? (
          <CheckIcon className="size-3.5" />
        ) : (
          <CopyIcon className="size-3.5" />
        )}
      </TooltipIconButton>
    </div>
  );
};
