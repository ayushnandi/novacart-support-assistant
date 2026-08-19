import type { FeedbackAdapter } from "@assistant-ui/react";
import { submitFeedback } from "./api";

export const feedbackAdapter: FeedbackAdapter = {
  submit: ({ type, message }) => {
    const messageId = (message.metadata?.custom?.messageId as string | undefined) ?? message.id;
    const rating = type === "positive" ? "up" : "down";
    void submitFeedback(messageId, rating);
  },
};
