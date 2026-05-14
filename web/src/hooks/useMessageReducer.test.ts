import { describe, it, expect } from 'vitest';
import { attachmentMessageToSteps } from './useMessageReducer';
import type { WebsocketMessage } from '../services/websocket';
import type { ImageContent } from '../types/message';

/**
 * Build a minimal ATTACHMENT-shaped WebsocketMessage. Tests pass
 * overrides via the partial parameter; we fill in safe defaults for
 * fields the reducer touches.
 */
function makeAttachmentMsg(
  partial: Partial<WebsocketMessage> = {},
): WebsocketMessage {
  return {
    type: 'attachment',
    content: '',
    is_user: false,
    is_final: true,
    metadata: {},
    ...partial,
  };
}

describe('attachmentMessageToSteps', () => {
  it('returns empty array when no attachments', () => {
    const steps = attachmentMessageToSteps(
      makeAttachmentMsg({ attachments: [] }),
    );
    expect(steps).toEqual([]);
  });

  it('returns empty array when attachments field is missing', () => {
    // Frontend should not crash on a malformed frame from a future
    // backend — defensive omission of attachments returns no steps
    // rather than throwing.
    const steps = attachmentMessageToSteps(makeAttachmentMsg());
    expect(steps).toEqual([]);
  });

  it('produces one step per image with shared msgId', () => {
    const steps = attachmentMessageToSteps(
      makeAttachmentMsg({
        msg_id: 'm-42',
        attachments: [
          {
            kind: 'image',
            url: '/api/media/s1/a.jpg',
            mime_type: 'image/jpeg',
            caption: 'Two views:',
          },
          {
            kind: 'image',
            url: '/api/media/s1/b.jpg',
            mime_type: 'image/jpeg',
            caption: 'Two views:',
          },
        ],
      }),
    );

    expect(steps).toHaveLength(2);
    // Same msg_id → reducer groups them into one assistant turn.
    expect(steps[0].msgId).toBe('m-42');
    expect(steps[1].msgId).toBe('m-42');
    // Composite ids keep React keys distinct.
    expect(steps[0].id).toBe('m-42_image_0');
    expect(steps[1].id).toBe('m-42_image_1');
    expect(steps[0].role).toBe('assistant');
    expect(steps[0].type).toBe('image');
  });

  it('renders caption only on the first image of a batch', () => {
    // Both wire-side attachments carry the caption (backend mirrors it
    // on every WebsocketAttachment), but the reducer dedupes so users
    // see one caption above the first image rather than three copies.
    const steps = attachmentMessageToSteps(
      makeAttachmentMsg({
        msg_id: 'm-99',
        attachments: [
          {
            kind: 'image',
            url: '/api/media/s1/a.jpg',
            mime_type: 'image/jpeg',
            caption: 'Three views:',
          },
          {
            kind: 'image',
            url: '/api/media/s1/b.jpg',
            mime_type: 'image/jpeg',
            caption: 'Three views:',
          },
          {
            kind: 'image',
            url: '/api/media/s1/c.jpg',
            mime_type: 'image/jpeg',
            caption: 'Three views:',
          },
        ],
      }),
    );

    expect((steps[0].content as ImageContent).caption).toBe('Three views:');
    expect((steps[1].content as ImageContent).caption).toBe('');
    expect((steps[2].content as ImageContent).caption).toBe('');
  });

  it('handles null caption from backend by falling back to empty string', () => {
    // ``echo_image`` without a caption arg gives display="Sent image"
    // and the wire still has a string. But raw payloads or future
    // tools may send caption=null; the rendered content must still be
    // a string so React renders it without warnings.
    const steps = attachmentMessageToSteps(
      makeAttachmentMsg({
        msg_id: 'm-1',
        attachments: [
          {
            kind: 'image',
            url: 'https://example.com/cat.jpg',
            mime_type: 'image/jpeg',
            caption: null,
          },
        ],
      }),
    );
    expect((steps[0].content as ImageContent).caption).toBe('');
  });

  it('passes URL and mime_type through unchanged', () => {
    const steps = attachmentMessageToSteps(
      makeAttachmentMsg({
        attachments: [
          {
            kind: 'image',
            url: 'https://example.com/cat.png',
            mime_type: 'image/png',
            caption: 'Look:',
          },
        ],
      }),
    );
    const content = steps[0].content as ImageContent;
    expect(content.url).toBe('https://example.com/cat.png');
    expect(content.mimeType).toBe('image/png');
  });

  it('synthesises a msgId when the frame omits one', () => {
    // Backend always sets msg_id today, but defensive-against-drift:
    // if it's missing, generate one so the reducer's groupStepsByMsgId
    // doesn't collapse multiple unrelated batches into one Message.
    const steps = attachmentMessageToSteps(
      makeAttachmentMsg({
        attachments: [
          {
            kind: 'image',
            url: '/api/media/s1/a.jpg',
            mime_type: 'image/jpeg',
            caption: '',
          },
        ],
      }),
    );
    expect(steps[0].msgId).toMatch(/^assistant_attachment_/);
  });

  it('uses provided speaker, falls back to Brain', () => {
    const withSpeaker = attachmentMessageToSteps(
      makeAttachmentMsg({
        speaker: 'Tank-Bot',
        attachments: [
          {
            kind: 'image',
            url: 'https://example.com/x.jpg',
            mime_type: 'image/jpeg',
            caption: '',
          },
        ],
      }),
    );
    expect(withSpeaker[0].speaker).toBe('Tank-Bot');

    const noSpeaker = attachmentMessageToSteps(
      makeAttachmentMsg({
        attachments: [
          {
            kind: 'image',
            url: 'https://example.com/x.jpg',
            mime_type: 'image/jpeg',
            caption: '',
          },
        ],
      }),
    );
    expect(noSpeaker[0].speaker).toBe('Brain');
  });

  it('forwards is_final to each step', () => {
    const finalSteps = attachmentMessageToSteps(
      makeAttachmentMsg({
        is_final: true,
        attachments: [
          {
            kind: 'image',
            url: 'https://example.com/x.jpg',
            mime_type: 'image/jpeg',
            caption: '',
          },
        ],
      }),
    );
    expect(finalSteps[0].isFinal).toBe(true);

    // Defensive: backend always sets is_final=true on attachment
    // frames, but if a future streaming-image variant lands, the
    // reducer should respect the flag rather than hardcoding.
    const draftSteps = attachmentMessageToSteps(
      makeAttachmentMsg({
        is_final: false,
        attachments: [
          {
            kind: 'image',
            url: 'https://example.com/x.jpg',
            mime_type: 'image/jpeg',
            caption: '',
          },
        ],
      }),
    );
    expect(draftSteps[0].isFinal).toBe(false);
  });
});
