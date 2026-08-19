import type { ChatModelAdapter, ThreadMessage } from "@assistant-ui/react";
import { streamChat } from "./api";

function getLastUserText(messages: readonly ThreadMessage[]): string {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "user") return "";
  const textPart = last.content.find((part) => part.type === "text");
  return textPart && "text" in textPart ? textPart.text : "";
}

export function createChatModelAdapter(getUserId: () => string): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const userMessage = getLastUserText(messages);
      let accumulated = "";

      for await (const event of streamChat(userMessage, getUserId(), abortSignal)) {
        if (event.type === "token") {
          accumulated += event.text;
          yield { content: [{ type: "text", text: accumulated }] };
        } else {
          yield {
            content: [{ type: "text", text: accumulated }],
            status: { type: "complete", reason: "stop" },
            metadata: {
              custom: {
                messageId: event.messageId,
                escalated: event.escalated,
                humanOffered: event.humanOffered,
                intent: event.intent,
                sentiment: event.sentiment,
                sources: event.sources,
              },
            },
          };
        }
      }
    },
  };
}
