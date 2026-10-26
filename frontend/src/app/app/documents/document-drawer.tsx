"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { DocumentStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Segmented, TokenInput } from "@/components/ui/controls";
import { Drawer } from "@/components/ui/dialog";
import { Field, FormError, Input, Select } from "@/components/ui/field";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { documentsApi } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/errors";
import type { Collection, HelpDocument } from "@/lib/api/types";
import { usePermissions } from "@/lib/auth/roles";
import { formatBytes, formatDateTime, formatNumber } from "@/lib/format";
import { useMutation, useQuery } from "@/lib/query";

type Tab = "text" | "chunks" | "details";

const TYPE_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word (DOCX)",
  "text/markdown": "Markdown",
  "text/plain": "Plain text",
  "text/html": "HTML",
};

export function documentTypeLabel(contentType: string): string {
  return TYPE_LABELS[contentType] ?? contentType;
}

function TextTab({ document }: { document: HelpDocument }) {
  const text = useQuery(`document-text:${document.id}:${document.updated_at}`, (signal) =>
    documentsApi.text(document.id, { signal }),
  );
  if (text.isLoading) return <LoadingBlock label="Loading text" />;
  if (text.error) return <ErrorState message={text.error.message} onRetry={text.refetch} />;
  if (!text.data?.text) {
    return (
      <EmptyState
        title="No text yet"
        description={
          document.status === "failed"
            ? document.error_message
            : "Text appears here once the document has been processed."
        }
      />
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {formatNumber(text.data.char_count)} characters
        {text.data.truncated && " (showing the first 200,000)"}
      </p>
      <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-surface-muted/40 p-4 font-sans text-sm leading-relaxed">
        {text.data.text}
      </pre>
    </div>
  );
}

function ChunksTab({ document }: { document: HelpDocument }) {
  const [page, setPage] = useState(1);
  const chunks = useQuery(`document-chunks:${document.id}:${document.updated_at}:${page}`, (signal) =>
    documentsApi.chunks(document.id, { page, page_size: 20 }, { signal }),
  );
  if (chunks.isLoading) return <LoadingBlock label="Loading passages" />;
  if (chunks.error) return <ErrorState message={chunks.error.message} onRetry={chunks.refetch} />;
  if (!chunks.data || chunks.data.count === 0) {
    return <EmptyState title="No passages yet" description="Passages are created when the document is indexed." />;
  }
  return (
    <div className="-mx-5">
      <p className="px-5 pb-3 text-xs text-muted-foreground">
        The retrievable passages the assistant searches, in document order.
      </p>
      <ol className="divide-y divide-border border-y border-border">
        {chunks.data.results.map((chunk) => (
          <li key={chunk.id} className="px-5 py-3">
            <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="rounded bg-surface-muted px-1.5 py-0.5 font-mono">#{chunk.ordinal + 1}</span>
              <span className="font-medium text-foreground">{chunk.location || chunk.heading || "Passage"}</span>
              <span>{chunk.token_count} tokens</span>
            </div>
            <p className="line-clamp-6 whitespace-pre-wrap text-sm leading-relaxed">{chunk.text}</p>
          </li>
        ))}
      </ol>
      <Pagination page={page} pageSize={20} count={chunks.data.count} onPageChange={setPage} label="passages" />
    </div>
  );
}

function DetailsTab({
  document,
  collections,
  onSaved,
}: {
  document: HelpDocument;
  collections: Collection[];
  onSaved: (document: HelpDocument) => void;
}) {
  const { isAdmin } = usePermissions();
  const toast = useToast();
  const [title, setTitle] = useState(document.title);
  const [tags, setTags] = useState(document.tags);
  const [collectionId, setCollectionId] = useState(document.collection?.id ?? "");
  const save = useMutation(() =>
    documentsApi.update(document.id, { title: title.trim(), tags, collection_id: collectionId || null }),
  );

  const rows: [string, string][] = [
    ["File", document.original_filename],
    ["Type", documentTypeLabel(document.content_type)],
    ["Size", formatBytes(document.file_size)],
    ["Pages", document.page_count === null ? "-" : String(document.page_count)],
    ["Passages", formatNumber(document.chunk_count)],
    ["Tokens", formatNumber(document.token_count)],
    ["Embedder", document.embedder || "-"],
    ["Uploaded by", document.uploaded_by?.full_name || document.uploaded_by?.email || "-"],
    ["Uploaded", formatDateTime(document.created_at)],
    ["Indexed", formatDateTime(document.processed_at)],
  ];

  return (
    <div className="space-y-6">
      {isAdmin && (
        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault();
            const updated = await save.mutate();
            if (updated) {
              onSaved(updated);
              toast.success("Document updated");
            }
          }}
        >
          <FormError message={save.error?.message} />
          <Field label="Title" error={save.error?.fieldErrors().title?.[0]}>
            {(props) => <Input {...props} value={title} maxLength={255} onChange={(event) => setTitle(event.target.value)} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Collection">
              {(props) => (
                <Select {...props} value={collectionId} onChange={(event) => setCollectionId(event.target.value)}>
                  <option value="">No collection</option>
                  {collections.map((collection) => (
                    <option key={collection.id} value={collection.id}>
                      {collection.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Tags">
              {(props) => (
                <TokenInput
                  id={props.id}
                  values={tags}
                  onChange={setTags}
                  max={10}
                  normalize={(value) => value.trim().toLowerCase().slice(0, 50)}
                />
              )}
            </Field>
          </div>
          <div className="flex justify-end">
            <Button type="submit" loading={save.pending} disabled={!title.trim()}>
              Save changes
            </Button>
          </div>
        </form>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function DocumentDrawer({
  document,
  collections,
  onClose,
  onChanged,
}: {
  document: HelpDocument | null;
  collections: Collection[];
  onClose: () => void;
  onChanged: (document: HelpDocument) => void;
}) {
  const [tab, setTab] = useState<Tab>("text");
  const { isAdmin } = usePermissions();
  const toast = useToast();
  const reindex = useMutation((id: string) => documentsApi.reindex(id), {
    onError: (error) => toast.error("Could not re-index", errorMessage(error)),
  });

  return (
    <Drawer
      open={document !== null}
      onClose={onClose}
      title={document?.title ?? "Document"}
      description={
        document && (
          <span className="flex flex-wrap items-center gap-2">
            <DocumentStatusBadge status={document.status} />
            <span>{document.original_filename}</span>
          </span>
        )
      }
      footer={
        document &&
        isAdmin && (
          <Button
            variant="outline"
            size="sm"
            loading={reindex.pending}
            icon={<RefreshCw className="size-4" aria-hidden />}
            onClick={async () => {
              const updated = await reindex.mutate(document.id);
              if (updated) {
                onChanged(updated);
                toast.success("Re-indexing started", "Status updates live as it runs.");
              }
            }}
          >
            Re-index
          </Button>
        )
      }
    >
      {document && (
        <div className="space-y-5">
          {document.status === "failed" && document.error_message && (
            <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
              {document.error_message}
            </p>
          )}
          <Segmented
            label="Document view"
            value={tab}
            onChange={setTab}
            size="md"
            options={[
              { value: "text", label: "Extracted text" },
              { value: "chunks", label: `Passages (${document.chunk_count})` },
              { value: "details", label: isAdmin ? "Details and edit" : "Details" },
            ]}
          />
          {tab === "text" && <TextTab document={document} />}
          {tab === "chunks" && <ChunksTab document={document} />}
          {tab === "details" && (
            <DetailsTab key={document.id} document={document} collections={collections} onSaved={onChanged} />
          )}
        </div>
      )}
    </Drawer>
  );
}
