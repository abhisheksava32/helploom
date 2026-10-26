"use client";

/**
 * Drag and drop upload. Each file is its own request so every row gets a real
 * progress bar and its own outcome (accepted, rejected with the server's reason,
 * or retryable). Two uploads run at a time to stay well inside the upload throttle.
 */

import { CheckCircle2, CircleAlert, FileUp, RotateCcw, UploadCloud, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { UpgradeNotice } from "@/components/upgrade-notice";
import { Button } from "@/components/ui/button";
import { TokenInput } from "@/components/ui/controls";
import { Field, Select } from "@/components/ui/field";
import { ApiError } from "@/lib/api/client";
import { documentsApi } from "@/lib/api/endpoints";
import { planLimitOf, retryAfterSeconds, type PlanLimit } from "@/lib/api/errors";
import type { Collection } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";

const ACCEPTED_EXTENSIONS = ["pdf", "docx", "md", "markdown", "txt", "html", "htm"];
const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(",");
/** Mirrors MAX_UPLOAD_MB's default so obvious mistakes fail fast; the server stays the authority. */
const MAX_BYTES = 20 * 1024 * 1024;
const CONCURRENCY = 2;

type UploadState = "waiting" | "uploading" | "done" | "rejected" | "error";

interface UploadItem {
  id: number;
  file: File;
  state: UploadState;
  progress: number;
  message: string;
  /** Settings at the time the file was added, so a retry uploads it the same way. */
  collectionId: string;
  tags: string[];
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
}

function precheck(file: File): string | null {
  if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name))) {
    return `${file.name} is not a PDF, DOCX, Markdown, TXT or HTML file.`;
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_BYTES) return `This file is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_BYTES)}.`;
  return null;
}

export function UploadPanel({
  collections,
  onUploaded,
}: {
  collections: Collection[];
  onUploaded: () => void;
}) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [collectionId, setCollectionId] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [planLimit, setPlanLimit] = useState<PlanLimit | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const queueRef = useRef<UploadItem[]>([]);
  const activeRef = useRef(0);
  const dragDepth = useRef(0);
  const lastId = useRef(0);

  const patch = (id: number, update: Partial<UploadItem>) =>
    setItems((list) => list.map((item) => (item.id === id ? { ...item, ...update } : item)));

  const pump = () => {
    while (activeRef.current < CONCURRENCY && queueRef.current.length > 0) {
      const item = queueRef.current.shift();
      if (item) void uploadOne(item);
    }
  };

  const uploadOne = async (item: UploadItem) => {
    activeRef.current += 1;
    patch(item.id, { state: "uploading", progress: 0, message: "" });
    try {
      const result = await documentsApi.upload(
        [item.file],
        { collectionId: item.collectionId || undefined, tags: item.tags },
        { onProgress: (fraction) => patch(item.id, { progress: fraction }) },
      );
      const rejected = result.rejected[0];
      if (rejected) patch(item.id, { state: "rejected", message: rejected.message });
      else patch(item.id, { state: "done", progress: 1, message: "Queued for indexing" });
      onUploaded();
    } catch (error) {
      const limit = planLimitOf(error);
      if (limit) {
        setPlanLimit(limit);
        // The rest would be refused for the same reason; stop the queue.
        for (const queued of queueRef.current) {
          patch(queued.id, { state: "error", message: "Not uploaded: the plan's document limit is reached." });
        }
        queueRef.current = [];
        patch(item.id, { state: "error", message: "The plan's document limit is reached." });
      } else if (error instanceof ApiError && error.code === "upload_rejected") {
        const rejected = (error.details.rejected as { message?: string }[] | undefined)?.[0];
        patch(item.id, { state: "rejected", message: rejected?.message ?? error.message });
      } else if (error instanceof ApiError && error.code === "throttled") {
        const wait = retryAfterSeconds(error.details);
        patch(item.id, { state: "error", message: `Too many uploads at once.${wait ? ` Retry in ${wait} s.` : ""}` });
      } else {
        patch(item.id, {
          state: "error",
          message: error instanceof Error ? error.message : "Upload failed.",
        });
      }
    } finally {
      activeRef.current -= 1;
      pump();
    }
  };

  const addFiles = (files: FileList | File[]) => {
    const added: UploadItem[] = [];
    for (const file of Array.from(files)) {
      lastId.current += 1;
      const problem = precheck(file);
      const item: UploadItem = {
        id: lastId.current,
        file,
        state: problem ? "rejected" : "waiting",
        progress: 0,
        message: problem ?? "",
        collectionId,
        tags,
      };
      added.push(item);
      if (!problem) queueRef.current.push(item);
    }
    setItems((list) => [...added.reverse(), ...list].slice(0, 50));
    setPlanLimit(null);
    pump();
  };

  const retry = (item: UploadItem) => {
    queueRef.current.push(item);
    patch(item.id, { state: "waiting", message: "" });
    pump();
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (event.dataTransfer.files.length > 0) addFiles(event.dataTransfer.files);
  };

  const finished = items.filter((item) => item.state !== "waiting" && item.state !== "uploading");

  return (
    <div className="space-y-4">
      <div
        onDragEnter={(event) => {
          event.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => {
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) setDragging(false);
        }}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-primary bg-accent" : "border-border bg-surface-muted/40",
        )}
      >
        <div className="mb-3 grid size-11 place-items-center rounded-xl bg-surface text-primary shadow-card">
          <UploadCloud className="size-5" aria-hidden />
        </div>
        <p className="text-sm font-medium">{dragging ? "Drop to upload" : "Drag files here"}</p>
        <p className="mt-1 text-xs text-muted-foreground">PDF, DOCX, Markdown, TXT or HTML, up to 20 MB each</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => inputRef.current?.click()}
          icon={<FileUp className="size-4" aria-hidden />}
        >
          Browse files
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          className="sr-only"
          tabIndex={-1}
          aria-label="Choose files to upload"
          onChange={(event) => {
            if (event.target.files) addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Collection" optional hint="Every file in this upload joins it.">
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
        <Field label="Tags" optional hint="Press Enter after each tag.">
          {(props) => (
            <TokenInput
              id={props.id}
              ariaDescribedBy={props["aria-describedby"]}
              values={tags}
              onChange={setTags}
              placeholder="billing, policy"
              max={10}
              normalize={(value) => value.trim().toLowerCase().slice(0, 50)}
            />
          )}
        </Field>
      </div>

      {planLimit && <UpgradeNotice limit={planLimit} />}

      {items.length > 0 && (
        <div className="rounded-lg border border-border">
          <div className="flex items-center justify-between border-b border-border px-4 py-2">
            <p className="text-xs font-medium text-muted-foreground">Uploads</p>
            {finished.length > 0 && (
              <button
                type="button"
                className="text-xs font-medium text-muted-foreground hover:text-foreground"
                onClick={() => setItems((list) => list.filter((item) => item.state === "waiting" || item.state === "uploading"))}
              >
                Clear finished
              </button>
            )}
          </div>
          <ul className="max-h-72 divide-y divide-border overflow-y-auto" aria-live="polite">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm">{item.file.name}</p>
                    <span className="shrink-0 text-xs text-muted-foreground">{formatBytes(item.file.size)}</span>
                  </div>
                  {item.state === "uploading" || item.state === "waiting" ? (
                    <div
                      role="progressbar"
                      aria-label={`Uploading ${item.file.name}`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(item.progress * 100)}
                      className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-accent"
                    >
                      <div
                        className="h-full rounded-full bg-primary transition-[width] duration-150"
                        style={{ width: `${Math.max(item.state === "waiting" ? 0 : 4, item.progress * 100)}%` }}
                      />
                    </div>
                  ) : (
                    <p
                      className={cn(
                        "mt-0.5 text-xs",
                        item.state === "done" ? "text-success" : "text-danger",
                      )}
                    >
                      {item.message}
                    </p>
                  )}
                </div>
                {item.state === "done" && <CheckCircle2 className="size-4 shrink-0 text-success" aria-label="Uploaded" />}
                {item.state === "rejected" && <CircleAlert className="size-4 shrink-0 text-danger" aria-label="Rejected" />}
                {item.state === "error" && (
                  <Button variant="ghost" size="icon-sm" aria-label={`Retry ${item.file.name}`} onClick={() => retry(item)}>
                    <RotateCcw className="size-4" aria-hidden />
                  </Button>
                )}
                {(item.state === "rejected" || item.state === "done") && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Dismiss ${item.file.name}`}
                    onClick={() => setItems((list) => list.filter((entry) => entry.id !== item.id))}
                  >
                    <X className="size-4" aria-hidden />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
