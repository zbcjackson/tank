/**
 * Centralized REST API client for the Tank backend.
 *
 * All HTTP requests to the backend should go through these functions.
 * Consumers don't need to know about URLs, httpFetch, response parsing,
 * or the apiBaseUrl — it's all handled internally.
 *
 * Usage:
 *   import * as api from '../services/api';
 *   const channels = await api.channels.list();
 *   const channel = await api.channels.create({ name: 'My Channel' });
 */

import { loadServerSettings } from './serverSettings';
import { httpFetch } from './httpClient';

/**
 * Error thrown when an API request fails.
 */
export class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Get the current API base URL from server settings.
 * Returns empty string for relative requests (dev proxy / same-origin).
 */
function getApiBaseUrl(): string {
  const settings = loadServerSettings();
  if (!settings) return '';
  return `${settings.protocol}://${settings.hostPort}`;
}

/**
 * Helper to throw a typed ApiError on non-ok responses.
 */
async function checkResponse(res: Response, context: string): Promise<Response> {
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body.detail;
    } catch {
      // No JSON body or parse failed
    }
    throw new ApiError(`${context}: HTTP ${res.status}`, res.status, detail);
  }
  return res;
}

/**
 * Build a full API URL using the current server settings.
 * Empty baseUrl → relative path (dev proxy / same-origin).
 */
function apiUrl(path: string): string {
  const baseUrl = getApiBaseUrl();
  return baseUrl ? `${baseUrl}${path}` : path;
}

// ============================================================================
// Channels
// ============================================================================

export interface ChannelInfo {
  slug: string;
  name: string;
  description: string;
  message_count: number;
  last_message_at: string;
  unread_count: number;
}

export interface CreateChannelRequest {
  name: string;
  slug?: string;
  description?: string;
}

export const channels = {
  /**
   * List all channels.
   */
  async list(): Promise<ChannelInfo[]> {
    const res = await httpFetch(apiUrl('/api/channels'));
    await checkResponse(res, 'Failed to fetch channels');
    return res.json();
  },

  /**
   * Get a single channel by slug.
   */
  async get(slug: string): Promise<ChannelInfo & { conversation_id?: string }> {
    const res = await httpFetch(apiUrl(`/api/channels/${slug}`));
    await checkResponse(res, 'Failed to fetch channel');
    return res.json();
  },

  /**
   * Create a new channel.
   */
  async create(data: CreateChannelRequest): Promise<ChannelInfo> {
    const res = await httpFetch(apiUrl('/api/channels'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: data.name,
        slug: data.slug || undefined,
        description: data.description || '',
      }),
    });
    await checkResponse(res, 'Failed to create channel');
    return res.json();
  },

  /**
   * Delete a channel by slug.
   */
  async delete(slug: string): Promise<void> {
    const res = await httpFetch(apiUrl(`/api/channels/${slug}`), {
      method: 'DELETE',
    });
    await checkResponse(res, 'Failed to delete channel');
  },

  /**
   * Mark a channel as read (clear unread count).
   */
  async markRead(slug: string): Promise<void> {
    const res = await httpFetch(apiUrl(`/api/channels/${slug}/read`), {
      method: 'PUT',
    });
    await checkResponse(res, 'Failed to mark channel as read');
  },
};

// ============================================================================
// Conversations
// ============================================================================

export interface ConversationInfo {
  id: string;
  start_time: string;
  updated_at: string;
  message_count: number;
  preview: string;
}

export interface HistoryMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  name?: string;
  msg_id: string;
  tool_calls?: Array<{
    id: string;
    type: string;
    function: {
      name: string;
      arguments: string;
    };
  }>;
  tool_call_id?: string;
  kind?: 'image';
  attachments?: Array<{
    kind: 'image';
    url: string;
    mime_type: string;
    caption: string | null;
  }>;
}

interface ConversationMessagesResponse {
  messages: HistoryMessage[];
}

export const conversations = {
  /**
   * List all conversations.
   */
  async list(): Promise<ConversationInfo[]> {
    const res = await httpFetch(apiUrl('/api/conversations'));
    await checkResponse(res, 'Failed to fetch conversations');
    return res.json();
  },

  /**
   * Get messages for a specific conversation.
   */
  async getMessages(conversationId: string): Promise<HistoryMessage[]> {
    const res = await httpFetch(apiUrl(`/api/conversations/${conversationId}/messages`));
    await checkResponse(res, 'Failed to fetch conversation messages');
    const data: ConversationMessagesResponse = await res.json();
    return data.messages;
  },
};

// ============================================================================
// Upload
// ============================================================================

export interface UploadRequest {
  file: File;
  sessionId: string;
}

export interface UploadResponse {
  media_uri: string;
  mime_type: string;
  size: number;
  modality: 'image' | 'file' | 'audio' | 'video';
}

export const upload = {
  /**
   * Upload a file attachment.
   */
  async file({ file, sessionId }: UploadRequest): Promise<UploadResponse> {
    const form = new FormData();
    form.append('file', file);
    const res = await httpFetch(
      apiUrl(`/api/upload?session_id=${encodeURIComponent(sessionId)}`),
      { method: 'POST', body: form },
    );
    await checkResponse(res, 'Upload failed');
    return res.json();
  },
};

// ============================================================================
// Users (Speaker Identification)
// ============================================================================

export interface UserInfo {
  user_id: string;
  name: string;
  sample_count: number;
}

export const users = {
  /**
   * List all enrolled users (speakers).
   */
  async list(): Promise<UserInfo[]> {
    const res = await httpFetch(apiUrl('/api/users'));
    await checkResponse(res, 'Failed to fetch users');
    return res.json();
  },
};

// ============================================================================
// Speakers (Enrollment)
// ============================================================================

export interface EnrollSpeakerRequest {
  audioBlob: Blob;
  name: string;
  userId?: string;
}

export const speakers = {
  /**
   * Enroll a speaker with an audio sample.
   */
  async enroll({ audioBlob, name, userId }: EnrollSpeakerRequest): Promise<void> {
    const form = new FormData();
    form.append('audio', audioBlob, 'enrollment.pcm');

    const params = new URLSearchParams({ name });
    if (userId) params.append('user_id', userId);

    const res = await httpFetch(apiUrl(`/api/speakers/enroll?${params.toString()}`), {
      method: 'POST',
      body: form,
    });
    await checkResponse(res, 'Enrollment failed');
  },
};
