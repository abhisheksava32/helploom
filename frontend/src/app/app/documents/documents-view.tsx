"use client";

import {
  ChevronDown,
  Eye,
  FileCode2,
  FileText,
  FileType2,
  Folder,
  MoreHorizontal,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CollectionsDialog } from "./collections-dialog";
import { DocumentDrawer } from "./document-drawer";
import { UploadPanel } from "./upload-panel";
import { DocumentStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/field";
import { Menu, MenuItem, MenuSeparator } from "@/components/ui/menu";
import { PageHeader, TableScroll, tableClasses } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { collectionsApi, documentsApi } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/errors";
import type { DocumentStatus, HelpDocument, Paginated } from "@/lib/api/types";
import { usePermissions } from "@/lib/auth/roles";
import { cn } from "@/lib/cn";
import { formatBytes, formatNumber, formatRelative } from "@/lib/format";
import { useDebouncedValue, useNow } from "@/lib/hooks";
import { invalidate, useMutation, useQuery } from "@/lib/query";
import { useDashboardEvents, useDashboardSocketStatus } from "@/lib/ws/dashboard";

const PAGE_SIZE = 25;

const ORDERINGS = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "title", label: "Title A to Z" },
  { value: "-file_size", label: "Largest first" },
  { value: "-chunk_count", label: "Most passages" },
  { value: "status", label: "Status" },
];

function FileIcon({ contentType }: { contentType: string }) {
  const Icon = contentType === "application/pdf" ? FileType2 : contentType === "text/html" ? FileCode2 : FileText;
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-md border border-border bg-surface-muted text-muted-foreground">
      <Icon className="size-4" aria-hidden />
    </span>
  );
}

function replaceDocument(list: Paginated<HelpDocument> | undefined, document: HelpDocument) {
  if (!list) return list;
  return { ...list, results: list.results.map((item) => (item.id === document.id ? document : item)) };
}

export function DocumentsView() {
  const { isAdmin } = usePermissions();
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const previewId = searchParams.get("preview");
  const now = useNow();
  const socketStatus = useDashboardSocketStatus();

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<DocumentStatus | "">("");
  const [collection, setCollection] = useState("");
  const [tag, setTag] = useState("");
  const [ordering, setOrdering] = useState("-created_at");
  const [page, setPage] = useState(1);
  const [showUpload, setShowUpload] = useState(false);
  const [collectionsOpen, setCollectionsOpen] = useState(false);
  const [deleting, setDeleting] = useState<HelpDocument | null>(null);
  const debouncedSearch = useDebouncedValue(search.trim(), 300);

  const filtered = Boolean(debouncedSearch || status || collection || tag);
  const query = { page, page_size: PAGE_SIZE, search: debouncedSearch, status, collection, tag, ordering };
  const documents = useQuery(`documents:${JSON.stringify(query)}`, (signal) => documentsApi.list(query, { signal }), {
    tags: ["documents"],
  });
  const collections = useQuery("collections:all", (signal) => collectionsApi.list({ page_size: 100 }, { signal }), {
    tags: ["collections"],
  });
  const tags = useQuery("documents:tags", (signal) => documentsApi.tags({ signal }), { tags: ["tags"] });
  const listed = documents.data?.results.find((item) => item.id === previewId);
  const single = useQuery(previewId && !listed ? `document:${previewId}` : null, (signal) =>
    documentsApi.get(previewId ?? "", { signal }),
  );
  const previewDocument = listed ?? (previewId ? single.data : undefined) ?? null;

  const remove = useMutation((id: string) => documentsApi.remove(id), {
    onError: (error) => toast.error("Could not delete the document", errorMessage(error)),
  });
  const reindex = useMutation((id: string) => documentsApi.reindex(id), {
    onError: (error) => toast.error("Could not re-index", errorMessage(error)),
  });

  // Live status: patch rows in place; a document this page has not seen means a
  // teammate uploaded something, so the list is refetched.
  useDashboardEvents((event) => {
    if (event.type === "document.status") {
      const known = documents.data?.results.some((item) => item.id === event.document.id);
      if (known) documents.setData((list) => replaceDocument(list, event.document));
      else if (page === 1 && !filtered) documents.refetch();
      if (event.document.id === previewId && !listed) single.setData(() => event.document);
      if (event.document.status === "ready" || event.document.status === "failed") invalidate("tags", "providers");
    } else if (event.type === "document.deleted") {
      documents.refetch();
    }
  });

  // Without the live socket, poll while anything is still being processed.
  const inFlight = documents.data?.results.some((item) => item.status === "queued" || item.status === "processing");
  const refetchDocuments = documents.refetch;
  useEffect(() => {
    if (!inFlight || socketStatus === "open") return;
    const timer = window.setInterval(refetchDocuments, 5000);
    return () => window.clearInterval(timer);
  }, [inFlight, socketStatus, refetchDocuments]);

  const openPreview = (id: string) => router.push(`${pathname}?preview=${id}`, { scroll: false });
  const closePreview = () => router.replace(pathname, { scroll: false });

  const updateFilter = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setPage(1);
  };

  const onReindex = async (document: HelpDocument) => {
    const updated = await reindex.mutate(document.id);
    if (updated) {
      documents.setData((list) => replaceDocument(list, updated));
      toast.success("Re-indexing started", document.title);
    }
  };

  const clearFilters = () => {
    setSearch("");
    setStatus("");
    setCollection("");
    setTag("");
    setPage(1);
  };

  const collectionList = collections.data?.results ?? [];
  const isEmptyLibrary = documents.data?.count === 0 && !filtered;
  // An empty library opens the upload panel, and it stays open once files arrive
  // so the upload queue does not vanish mid-upload (state adjusted during render).
  if (isEmptyLibrary && isAdmin && !showUpload) setShowUpload(true);

  return (
    <>
      <PageHeader
        title="Documents"
        description="The knowledge base the assistant answers from. Every upload is extracted, split into passages and embedded for hybrid search."
        actions={
          <>
            {isAdmin && (
              <Button variant="outline" onClick={() => setCollectionsOpen(true)} icon={<Folder className="size-4" aria-hidden />}>
                Collections
              </Button>
            )}
            {isAdmin && (
              <Button
                onClick={() => setShowUpload((value) => !value)}
                aria-expanded={showUpload}
                icon={<Upload className="size-4" aria-hidden />}
              >
                Upload
                <ChevronDown className={cn("size-4 transition-transform", showUpload && "rotate-180")} aria-hidden />
              </Button>
            )}
          </>
        }
      />

      {isAdmin && showUpload && (
        <Card className="mb-6">
          <CardBody>
            <UploadPanel collections={collectionList} onUploaded={() => invalidate("documents", "subscription")} />
          </CardBody>
        </Card>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              type="search"
              aria-label="Search documents by title or filename"
              placeholder="Search title or filename"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              className="pl-9"
            />
          </div>
          <Select
            aria-label="Filter by status"
            value={status}
            onChange={(event) => updateFilter(setStatus)(event.target.value as DocumentStatus | "")}
            className="w-auto"
          >
            <option value="">All statuses</option>
            <option value="ready">Ready</option>
            <option value="processing">Processing</option>
            <option value="queued">Queued</option>
            <option value="failed">Failed</option>
          </Select>
          <Select
            aria-label="Filter by collection"
            value={collection}
            onChange={(event) => updateFilter(setCollection)(event.target.value)}
            className="w-auto max-w-48"
          >
            <option value="">All collections</option>
            <option value="none">No collection</option>
            {collectionList.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Filter by tag"
            value={tag}
            onChange={(event) => updateFilter(setTag)(event.target.value)}
            className="w-auto max-w-44"
          >
            <option value="">All tags</option>
            {(tags.data?.results ?? []).map((item) => (
              <option key={item.tag} value={item.tag}>
                {item.tag} ({item.count})
              </option>
            ))}
          </Select>
          <Select
            aria-label="Sort documents"
            value={ordering}
            onChange={(event) => updateFilter(setOrdering)(event.target.value)}
            className="w-auto"
          >
            {ORDERINGS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>

        {documents.isLoading ? (
          <SkeletonRows rows={6} />
        ) : documents.error && !documents.data ? (
          <ErrorState message={documents.error.message} onRetry={documents.refetch} />
        ) : documents.data && documents.data.results.length > 0 ? (
          <div className={cn("transition-opacity", documents.isFetching && "opacity-70")}>
            <TableScroll>
              <table className={tableClasses.table}>
                <thead className={tableClasses.head}>
                  <tr>
                    <th scope="col" className={tableClasses.th}>
                      Document
                    </th>
                    <th scope="col" className={tableClasses.th}>
                      Status
                    </th>
                    <th scope="col" className={cn(tableClasses.th, "hidden text-right md:table-cell")}>
                      Passages
                    </th>
                    <th scope="col" className={cn(tableClasses.th, "hidden text-right lg:table-cell")}>
                      Size
                    </th>
                    <th scope="col" className={cn(tableClasses.th, "hidden md:table-cell")}>
                      Updated
                    </th>
                    <th scope="col" className={cn(tableClasses.th, "w-12")}>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {documents.data.results.map((document) => (
                    <tr key={document.id} className={tableClasses.row}>
                      <td className={tableClasses.td}>
                        <div className="flex items-center gap-3">
                          <FileIcon contentType={document.content_type} />
                          <div className="min-w-0">
                            <button
                              type="button"
                              onClick={() => openPreview(document.id)}
                              className="block max-w-[11rem] truncate text-left font-medium hover:text-primary hover:underline sm:max-w-xs"
                            >
                              {document.title}
                            </button>
                            <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                              <span className="max-w-48 truncate">{document.original_filename}</span>
                              {document.collection && (
                                <span className="inline-flex items-center gap-1">
                                  <Folder className="size-3" aria-hidden />
                                  {document.collection.name}
                                </span>
                              )}
                              {document.tags.map((item) => (
                                <span key={item} className="rounded bg-surface-muted px-1.5 py-px">
                                  {item}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className={tableClasses.td}>
                        <DocumentStatusBadge status={document.status} />
                        {document.status === "failed" && document.error_message && (
                          <p className="mt-1 max-w-56 text-xs text-danger">{document.error_message}</p>
                        )}
                      </td>
                      <td className={cn(tableClasses.td, "hidden text-right tabular-nums md:table-cell")}>
                        {document.status === "ready" ? formatNumber(document.chunk_count) : "-"}
                      </td>
                      <td className={cn(tableClasses.td, "hidden text-right tabular-nums text-muted-foreground lg:table-cell")}>
                        {formatBytes(document.file_size)}
                      </td>
                      <td className={cn(tableClasses.td, "hidden whitespace-nowrap text-muted-foreground md:table-cell")}>
                        {formatRelative(document.updated_at, now)}
                      </td>
                      <td className={tableClasses.td}>
                        <Menu
                          label={`Actions for ${document.title}`}
                          align="end"
                          triggerClassName="grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-surface-muted hover:text-foreground"
                          trigger={<MoreHorizontal className="size-4" aria-hidden />}
                        >
                          <MenuItem onClick={() => openPreview(document.id)}>
                            <Eye className="size-4" aria-hidden />
                            Preview text and passages
                          </MenuItem>
                          {isAdmin && (
                            <>
                              <MenuItem onClick={() => void onReindex(document)}>
                                <RefreshCw className="size-4" aria-hidden />
                                Re-index
                              </MenuItem>
                              <MenuSeparator />
                              <MenuItem onClick={() => setDeleting(document)} className="text-danger">
                                <Trash2 className="size-4" aria-hidden />
                                Delete
                              </MenuItem>
                            </>
                          )}
                        </Menu>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
            <Pagination page={page} pageSize={PAGE_SIZE} count={documents.data.count} onPageChange={setPage} label="documents" />
          </div>
        ) : filtered ? (
          <EmptyState
            icon={Search}
            title="No documents match these filters"
            action={
              <Button variant="outline" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={FileText}
            title="Your library is empty"
            description={
              isAdmin
                ? "Upload your policies, FAQs and handbooks above. The assistant can answer as soon as the first one is ready."
                : "An admin needs to upload documents before the assistant can answer."
            }
          />
        )}
      </Card>

      <DocumentDrawer
        document={previewDocument}
        collections={collectionList}
        onClose={closePreview}
        onChanged={(updated) => {
          documents.setData((list) => replaceDocument(list, updated));
          if (!listed) single.setData(() => updated);
          invalidate("tags");
        }}
      />

      <CollectionsDialog open={collectionsOpen} onClose={() => setCollectionsOpen(false)} collections={collectionList} />

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title={`Delete ${deleting?.title ?? "document"}?`}
        description="The file, its passages and its vectors are removed. Past answers keep their copied citations."
        confirmLabel="Delete document"
        pending={remove.pending}
        onConfirm={async () => {
          if (!deleting) return;
          const id = deleting.id;
          await remove.mutate(id);
          setDeleting(null);
          if (id === previewId) closePreview();
          invalidate("documents", "subscription", "tags");
        }}
      />
    </>
  );
}
