/**
 * Strip of attachment thumbnails above the chat input.
 *
 * Each chip shows a preview (image thumb or file icon), current upload
 * status, and a remove button. Errors surface in-place instead of a
 * toast — users can see exactly which attachment failed and why.
 */
import { X, FileText, AlertCircle, Loader2 } from 'lucide-react';
import type { Attachment } from '../../hooks/useUpload';

interface Props {
  attachments: Attachment[];
  onRemove: (id: string) => void;
}

function formatSize(bytes: number | undefined): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const AttachmentChips = ({ attachments, onRemove }: Props) => {
  if (attachments.length === 0) return null;

  return (
    <div
      className="max-w-3xl mx-auto px-1 pb-2 flex flex-wrap gap-2"
      data-testid="attachment-chips"
    >
      {attachments.map((att) => {
        const isImage = att.file.type.startsWith('image/');
        const isError = att.status === 'error';
        const isUploading = att.status === 'uploading';

        return (
          <div
            key={att.id}
            className={[
              'relative group flex items-center gap-2 pl-2 pr-7 py-1.5 rounded-lg border text-[11px]',
              isError
                ? 'border-red-500/40 bg-red-500/10 text-red-200'
                : 'border-border-subtle bg-surface-raised text-text-secondary',
            ].join(' ')}
            title={att.errorMessage || att.file.name}
            data-testid={`attachment-chip-${att.id}`}
          >
            {/* Preview: image thumbnail, file icon, or error icon */}
            {isError ? (
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
            ) : isImage && att.previewUrl ? (
              <img
                src={att.previewUrl}
                alt=""
                className="w-6 h-6 rounded object-cover shrink-0"
              />
            ) : (
              <FileText className="w-4 h-4 text-text-muted shrink-0" />
            )}

            <span className="truncate max-w-[160px] font-mono">
              {att.file.name}
            </span>

            {isUploading ? (
              <Loader2 className="w-3 h-3 animate-spin text-amber-400" />
            ) : isError ? null : (
              <span className="text-text-muted">{formatSize(att.size)}</span>
            )}

            <button
              type="button"
              onClick={() => onRemove(att.id)}
              aria-label={`Remove ${att.file.name}`}
              className="absolute top-0.5 right-0.5 p-0.5 rounded hover:bg-surface-overlay opacity-60 hover:opacity-100 transition-opacity"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
