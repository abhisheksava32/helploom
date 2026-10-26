"use client";

import { Check, FolderPlus, Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, FormError, Input } from "@/components/ui/field";
import { EmptyState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { collectionsApi } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/errors";
import type { Collection } from "@/lib/api/types";
import { pluralize } from "@/lib/format";
import { invalidate, useMutation } from "@/lib/query";

function CollectionRow({ collection, onChanged }: { collection: Collection; onChanged: () => void }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(collection.name);
  const [confirming, setConfirming] = useState(false);
  const rename = useMutation(() => collectionsApi.update(collection.id, { name: name.trim() }));
  const remove = useMutation(() => collectionsApi.remove(collection.id), {
    onError: (error) => toast.error("Could not delete the collection", errorMessage(error)),
  });

  if (editing) {
    return (
      <li className="flex items-center gap-2 py-2.5">
        <form
          className="flex flex-1 items-center gap-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await rename.mutate()) {
              setEditing(false);
              onChanged();
            }
          }}
        >
          <Input
            aria-label="Collection name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            aria-invalid={rename.error ? true : undefined}
            autoFocus
          />
          <Button type="submit" size="icon-sm" aria-label="Save name" loading={rename.pending} disabled={!name.trim()}>
            {!rename.pending && <Check className="size-4" aria-hidden />}
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label="Cancel rename" onClick={() => setEditing(false)}>
            <X className="size-4" aria-hidden />
          </Button>
        </form>
        {rename.error && <p className="text-xs text-danger">{rename.error.message}</p>}
      </li>
    );
  }

  return (
    <li className="flex items-center gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{collection.name}</p>
        <p className="text-xs text-muted-foreground">{pluralize(collection.document_count, "document")}</p>
      </div>
      {confirming ? (
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">Documents stay.</span>
          <Button
            variant="danger"
            size="sm"
            loading={remove.pending}
            onClick={async () => {
              await remove.mutate();
              setConfirming(false);
              onChanged();
            }}
          >
            Delete
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
            Keep
          </Button>
        </div>
      ) : (
        <>
          <Button variant="ghost" size="icon-sm" aria-label={`Rename ${collection.name}`} onClick={() => setEditing(true)}>
            <Pencil className="size-4" aria-hidden />
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label={`Delete ${collection.name}`} onClick={() => setConfirming(true)}>
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </>
      )}
    </li>
  );
}

export function CollectionsDialog({
  open,
  onClose,
  collections,
}: {
  open: boolean;
  onClose: () => void;
  collections: Collection[];
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useMutation(() => collectionsApi.create({ name: name.trim(), description: description.trim() }));
  const changed = () => invalidate("collections", "documents");

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Collections"
      description="Group documents by topic, for example Billing or Shipping. Filters and uploads can use them."
    >
      <form
        className="space-y-3 rounded-lg border border-border bg-surface-muted/40 p-4"
        onSubmit={async (event) => {
          event.preventDefault();
          if (await create.mutate()) {
            setName("");
            setDescription("");
            changed();
          }
        }}
      >
        <FormError message={create.error && !create.error.fieldErrors().name ? create.error.message : null} />
        <Field label="New collection" error={create.error?.fieldErrors().name?.[0]}>
          {(props) => (
            <Input {...props} value={name} maxLength={100} onChange={(event) => setName(event.target.value)} placeholder="Billing" />
          )}
        </Field>
        <Field label="Description" optional>
          {(props) => (
            <Input
              {...props}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Invoices, refunds and payment methods."
            />
          )}
        </Field>
        <div className="flex justify-end">
          <Button type="submit" size="sm" loading={create.pending} disabled={!name.trim()} icon={<FolderPlus className="size-4" aria-hidden />}>
            Add collection
          </Button>
        </div>
      </form>
      {collections.length === 0 ? (
        <EmptyState title="No collections yet" className="py-8" />
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {collections.map((collection) => (
            <CollectionRow key={collection.id} collection={collection} onChanged={changed} />
          ))}
        </ul>
      )}
    </Dialog>
  );
}
