import type { ImageContent } from '../../types/message';

interface ImageBubbleProps {
  content: ImageContent;
}

/**
 * Phase 17: assistant-sent image rendered inline in the conversation.
 *
 * Mirrors :class:`TextBubble`'s assistant-side bubble styling so the
 * image sits naturally in the message stream rather than as a separate
 * floating card. The optional caption renders above the image as
 * ordinary text — that matches how Telegram/Slack/Discord render their
 * native captioned-image messages, so users get a consistent shape
 * across surfaces.
 *
 * The ``url`` is always something the browser can fetch directly:
 *   - ``media://`` URIs were rewritten to ``/api/media/...`` server-side.
 *   - ``http(s)://`` URLs (e.g. from ``echo_image``) pass through.
 *
 * No loading skeleton: real-world image sizes are tiny (a few KB) and
 * a flicker-free immediate <img> render matches the connector
 * experience better than a spinner-then-image transition.
 */
export const ImageBubble = ({ content }: ImageBubbleProps) => (
  <div
    className="px-4 py-3 rounded-2xl text-[14px] leading-relaxed bg-surface-raised text-text-primary border border-border-subtle rounded-tl-sm"
    data-testid="assistant-image"
  >
    {content.caption ? (
      <div className="mb-2 whitespace-pre-wrap">{content.caption}</div>
    ) : null}
    <img
      src={content.url}
      alt={content.caption || 'Assistant-sent image'}
      // ``max-h`` clamps oversized photos so they don't push the
      // message stream out of view; ``rounded-lg`` matches the
      // bubble's outer corners on the inside edge.
      className="max-w-full max-h-[480px] rounded-lg"
      // No fetchpriority hint — browsers default to "auto" for images
      // discovered via DOM, and Tank's outbound images are already
      // small enough that a hint wouldn't change the user experience.
      loading="lazy"
    />
  </div>
);
