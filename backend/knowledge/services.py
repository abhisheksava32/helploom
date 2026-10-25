"""Document library and ingestion logic. Owner: backend-ai.

Planned entry points:

    accept_uploads(organization, files, uploaded_by, collection, tags) -> UploadResult
        Validates size and sniffed type, calls billing.services.ensure_document_quota,
        stores the files and queues ingestion with core.background.run_in_background.
    ingest_document(document_id) -> None
        extract (knowledge.extractors) -> chunk (knowledge.chunking) -> embed
        (knowledge.embeddings) -> store Chunks. Publishes document.status events with
        core.realtime.broadcast_org_event at every status change.
    reindex_document(document) / delete_document(document)

Retrieval itself lives in assistant.retrieval, which reads knowledge.Chunk.
"""
