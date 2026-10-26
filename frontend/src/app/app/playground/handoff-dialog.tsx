"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, FormError, Input, Textarea } from "@/components/ui/field";
import type { HandoffInput } from "@/lib/chat/use-chat";

export function HandoffDialog({
  open,
  onClose,
  defaultEmail,
  defaultName,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  defaultEmail: string;
  defaultName: string;
  onSubmit: (input: HandoffInput) => Promise<void>;
}) {
  const [email, setEmail] = useState(defaultEmail);
  const [name, setName] = useState(defaultName);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Hand off to a person"
      description="Creates a ticket on this conversation, the same way the website widget's Talk to a human button does."
    >
      <form
        id="handoff-form"
        className="space-y-4"
        onSubmit={async (event) => {
          event.preventDefault();
          setPending(true);
          setError(null);
          try {
            await onSubmit({ email: email.trim(), name: name.trim() || undefined, note: note.trim() || undefined });
            setNote("");
            onClose();
          } catch (caught) {
            setError(caught instanceof Error ? caught.message : "The handoff could not be created.");
          } finally {
            setPending(false);
          }
        }}
      >
        <FormError message={error} />
        <Field label="Requester email">
          {(props) => (
            <Input {...props} type="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          )}
        </Field>
        <Field label="Name" optional>
          {(props) => <Input {...props} value={name} maxLength={150} onChange={(event) => setName(event.target.value)} />}
        </Field>
        <Field label="Note for the team" optional>
          {(props) => (
            <Textarea
              {...props}
              value={note}
              maxLength={2000}
              onChange={(event) => setNote(event.target.value)}
              placeholder="What still needs an answer?"
            />
          )}
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending} disabled={!email.trim()}>
            Create ticket
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
