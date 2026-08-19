import { Thread } from "@/components/thread";
import { SupportAssistantMessage } from "@/components/support-assistant-message";
import { HelpPanel } from "@/components/help-panel";
import { SessionBadge } from "@/components/session-badge";
import { createChatModelAdapter } from "@/lib/chatAdapter";
import { feedbackAdapter } from "@/lib/feedbackAdapter";
import { getSessionId } from "@/lib/api";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { useEffect, useMemo, useRef, useState } from "react";

function App() {
  const [userId, setUserId] = useState("");
  const userIdRef = useRef(userId);
  userIdRef.current = userId;

  const [sessionId, setSessionId] = useState<string | null>(null);
  useEffect(() => {
    getSessionId().then(setSessionId);
  }, []);

  const chatModelAdapter = useMemo(
    () => createChatModelAdapter(() => userIdRef.current),
    [],
  );
  const runtime = useLocalRuntime(chatModelAdapter, {
    adapters: { feedback: feedbackAdapter },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-svh flex-col">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <div className="flex items-center gap-3">
            <h1 className="text-sm font-semibold">NovaCart Support</h1>
            <SessionBadge sessionId={sessionId} />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-muted-foreground flex items-center gap-2 text-xs">
              Demo user id (optional)
              <input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="ayush"
                className="border-border w-28 rounded-md border bg-transparent px-2 py-1 text-xs outline-none"
              />
            </label>
            <HelpPanel />
          </div>
        </header>
        <div className="min-h-0 flex-1">
          <Thread components={{ AssistantMessage: SupportAssistantMessage }} />
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
}

export default App;
