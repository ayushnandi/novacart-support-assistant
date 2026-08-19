import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { HelpCircleIcon } from "lucide-react";
import type { FC } from "react";

export const HelpPanel: FC = () => {
  return (
    <Dialog>
      <DialogTrigger
        render={<Button variant="ghost" size="icon-sm" aria-label="How to use" />}
      >
        <HelpCircleIcon className="size-4" />
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>How to use NovaCart Support</DialogTitle>
          <DialogDescription>
            A quick guide to what this assistant can do.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium">What it can answer</p>
            <p className="text-muted-foreground">
              Order tracking, refunds &amp; cancellations, returns &amp; exchanges,
              payments &amp; pricing, shipping, account &amp; membership, and technical
              issues — grounded only in NovaCart's real policies, never invented.
            </p>
          </div>

          <div>
            <p className="font-medium">When it hands off to a human</p>
            <p className="text-muted-foreground">
              You'll see an <span className="font-medium">"Handed to agent"</span> tag
              when: your question is outside NovaCart's FAQs, you sound frustrated, or
              you directly ask for a human (e.g. "talk to a person").
            </p>
          </div>

          <div>
            <p className="font-medium">Sources</p>
            <p className="text-muted-foreground">
              Grounded replies show the FAQ entries they were based on, right under the
              answer.
            </p>
          </div>

          <div>
            <p className="font-medium">Feedback</p>
            <p className="text-muted-foreground">
              Use the thumbs up/down under any reply to rate it — this is logged and
              helps flag answers that need improvement.
            </p>
          </div>

          <div>
            <p className="font-medium">Demo user id</p>
            <p className="text-muted-foreground">
              Enter a demo id (try <span className="font-mono">ayush</span> or{" "}
              <span className="font-mono">demo</span>) in the header to get a
              personalized greeting and order-aware answers.
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
