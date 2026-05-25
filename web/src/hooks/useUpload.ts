/**
 * Hook for uploading multi-modal attachments to the backend.
 *
 * Each file goes through POST /api/upload. The server gates uploads
 * by the current LLM's capabilities (HTTP 415 when the model can't
 * consume the MIME type) and by size (HTTP 413 at 25MB). Callers get
 * a `{media_uri, mime_type, size, modality}` record on success — that
 * record then rides on the WebSocket `input` message as metadata so
 * the assistant can reference the uploaded file in its reply.
 *
 * The hook owns no UI. Consumers render their own thumbnails/errors.
 */
import { useCallback, useState } from 'react';

import * as api from '../services/api';

export interface Attachment {
  /** Unique client-side id — used for list keys and removal. */
  id: string;
  /** Local File handle; kept so we can generate a preview thumbnail. */
  file: File;
  /** Object URL for thumbnail rendering; revoke when removed. */
  previewUrl: string | null;
  status: 'uploading' | 'uploaded' | 'error';
  /** Populated when status === 'uploaded'. */
  mediaUri?: string;
  mimeType?: string;
  size?: number;
  modality?: 'image' | 'file' | 'audio' | 'video';
  /** Populated when status === 'error'. */
  errorMessage?: string;
}

function nextId(): string {
  // Short non-crypto id; collisions don't matter for UI list keys.
  return `att_${Math.random().toString(36).slice(2, 10)}`;
}

function previewFor(file: File): string | null {
  // Only images get a thumbnail. PDFs and others get a generic icon in the UI.
  return file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
}

/**
 * Immutable state transition helper — replace one attachment by id,
 * leave the rest alone.
 */
function replaceById(
  list: Attachment[],
  id: string,
  patch: Partial<Attachment>,
): Attachment[] {
  return list.map((a) => (a.id === id ? { ...a, ...patch } : a));
}

export function useUpload(sessionId: string) {
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  const upload = useCallback(
    async (files: File[] | FileList) => {
      const fileArr = Array.from(files);
      if (!fileArr.length || !sessionId) return;

      // Seed optimistic entries so thumbnails appear immediately.
      const seeds: Attachment[] = fileArr.map((file) => ({
        id: nextId(),
        file,
        previewUrl: previewFor(file),
        status: 'uploading',
      }));
      setAttachments((prev) => [...prev, ...seeds]);

      await Promise.all(
        seeds.map(async (seed) => {
          try {
            const body = await api.upload.file({ file: seed.file, sessionId });
            setAttachments((prev) =>
              replaceById(prev, seed.id, {
                status: 'uploaded',
                mediaUri: body.media_uri,
                mimeType: body.mime_type,
                size: body.size,
                modality: body.modality,
              }),
            );
          } catch (e) {
            const msg = e instanceof Error ? e.message : 'Upload failed';
            setAttachments((prev) =>
              replaceById(prev, seed.id, { status: 'error', errorMessage: msg }),
            );
          }
        }),
      );
    },
    [sessionId],
  );

  /** Remove one attachment by id; revokes its preview URL to free memory. */
  const remove = useCallback((id: string) => {
    setAttachments((prev) => {
      const target = prev.find((a) => a.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((a) => a.id !== id);
    });
  }, []);

  /** Drop everything — called after a successful send. */
  const clear = useCallback(() => {
    setAttachments((prev) => {
      prev.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
      return [];
    });
  }, []);

  return { attachments, upload, remove, clear };
}
