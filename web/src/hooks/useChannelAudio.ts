import { useState, useCallback, useRef, useEffect } from 'react';

import { AudioPlayback } from '../services/audioPlayback';
import { createPlatformAudio, type PlatformAudioAdapter } from '../services/platformAudio';
import type { VoiceAssistantClient, WebsocketMessage } from '../services/websocket';

const STORAGE_KEY = 'tank.channelSubscriptions';

interface UseChannelAudioArgs {
  clientRef: React.RefObject<VoiceAssistantClient | null>;
}

function loadStoredSubscriptions(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) return new Set(arr.filter((s): s is string => typeof s === 'string'));
  } catch {
    // ignore
  }
  return new Set();
}

function storeSubscriptions(slugs: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(slugs)));
  } catch {
    // ignore
  }
}

/**
 * Manages a second audio playback track for channel audio (cron job deliveries
 * and interactive fan-out from other clients on the same channel).
 *
 * Binary frames arriving between channel_audio_start and channel_audio_end
 * signals are routed to this track instead of the interactive playback.
 *
 * Subscriptions are fully manual — user toggles via UI. Persisted in
 * localStorage and re-sent on each reconnect.
 */
export function useChannelAudio({ clientRef }: UseChannelAudioArgs) {
  const [isChannelAudioPlaying, setIsChannelAudioPlaying] = useState(false);
  const [channelAudioSlug, setChannelAudioSlug] = useState<string | null>(null);
  const [subscribedChannels, setSubscribedChannels] = useState<Set<string>>(() =>
    loadStoredSubscriptions(),
  );
  const channelAudioActiveRef = useRef(false);
  // When true, incoming channel chunks are dropped instead of played.
  // Set by user-initiated stop; cleared when the next channel_audio_start arrives.
  const droppingChunksRef = useRef(false);
  const playbackRef = useRef<AudioPlayback | null>(null);
  // Channel audio owns its own adapter/AudioContext so stopping doesn't cut interactive audio
  const adapterRef = useRef<PlatformAudioAdapter | null>(null);

  // Create a dedicated AudioPlayback + its own PlatformAudioAdapter.
  // The dedicated adapter gives channel audio its own AudioContext, so
  // stopChannelAudio() can close it without affecting the interactive track.
  useEffect(() => {
    const playback = new AudioPlayback();
    playbackRef.current = playback;
    playback.setOnSpeakingChange((speaking) => {
      setIsChannelAudioPlaying(speaking);
    });

    let disposed = false;
    createPlatformAudio((error) => {
      console.error('[useChannelAudio] Platform audio error:', error);
    }).then((adapter) => {
      if (disposed) {
        adapter.dispose();
        return;
      }
      adapterRef.current = adapter;
      playback.setPlatformAdapter(adapter);
    });

    return () => {
      disposed = true;
      playback.dispose();
      playbackRef.current = null;
      adapterRef.current?.dispose();
      adapterRef.current = null;
    };
  }, []);

  /**
   * Handle incoming signal messages related to channel audio.
   * Returns true if the message was consumed.
   */
  const handleSignal = useCallback((msg: WebsocketMessage): boolean => {
    if (msg.type !== 'signal') return false;

    if (msg.content === 'channel_audio_start') {
      channelAudioActiveRef.current = true;
      droppingChunksRef.current = false;
      const slug = (msg.metadata as Record<string, unknown>)?.channel_slug as string | undefined;
      setChannelAudioSlug(slug ?? null);
      playbackRef.current?.reset();
      return true;
    }

    if (msg.content === 'channel_audio_end') {
      channelAudioActiveRef.current = false;
      droppingChunksRef.current = false;
      setChannelAudioSlug(null);
      return true;
    }

    return false;
  }, []);

  const isChannelAudioActive = useCallback(() => channelAudioActiveRef.current, []);

  const playChannelChunk = useCallback((data: ArrayBuffer) => {
    if (droppingChunksRef.current) return;
    playbackRef.current?.play(data);
  }, []);

  /**
   * Stop the currently-playing channel audio.
   *
   * 1. Tells the server to interrupt TTS generation (stops more chunks arriving).
   * 2. Drops any in-flight chunks already on the wire.
   * 3. Calls AudioPlayback.stop() which closes the dedicated AudioContext —
   *    this cancels any chunks already scheduled in Web Audio, so playback
   *    stops immediately. Interactive audio is unaffected because it uses a
   *    separate AudioContext.
   */
  const stopChannelAudio = useCallback(() => {
    const slug = channelAudioActiveRef.current ? channelAudioSlug : null;
    clientRef.current?.sendMessage(
      'signal',
      'stop_channel_audio',
      slug ? { channel_slug: slug } : {},
    );
    droppingChunksRef.current = true;
    channelAudioActiveRef.current = false;
    setChannelAudioSlug(null);
    playbackRef.current?.stop();
  }, [channelAudioSlug, clientRef]);

  // --- Subscription management ---

  const sendSubscriptions = useCallback(
    (slugs: string[]) => {
      clientRef.current?.sendMessage('signal', 'subscribe_channels', { channels: slugs });
    },
    [clientRef],
  );

  const sendUnsubscriptions = useCallback(
    (slugs: string[]) => {
      clientRef.current?.sendMessage('signal', 'unsubscribe_channels', { channels: slugs });
    },
    [clientRef],
  );

  const isSubscribed = useCallback(
    (slug: string) => subscribedChannels.has(slug),
    [subscribedChannels],
  );

  const subscribe = useCallback(
    (slug: string) => {
      setSubscribedChannels((prev) => {
        if (prev.has(slug)) return prev;
        const next = new Set(prev);
        next.add(slug);
        storeSubscriptions(next);
        sendSubscriptions([slug]);
        return next;
      });
    },
    [sendSubscriptions],
  );

  const unsubscribe = useCallback(
    (slug: string) => {
      setSubscribedChannels((prev) => {
        if (!prev.has(slug)) return prev;
        const next = new Set(prev);
        next.delete(slug);
        storeSubscriptions(next);
        sendUnsubscriptions([slug]);
        return next;
      });
    },
    [sendUnsubscriptions],
  );

  const toggleSubscription = useCallback(
    (slug: string) => {
      if (subscribedChannels.has(slug)) {
        unsubscribe(slug);
      } else {
        subscribe(slug);
      }
    },
    [subscribedChannels, subscribe, unsubscribe],
  );

  // Re-subscribe to all persisted channels on connect/reconnect
  const resubscribeAll = useCallback(() => {
    const slugs = Array.from(subscribedChannels);
    if (slugs.length > 0) {
      sendSubscriptions(slugs);
    }
  }, [subscribedChannels, sendSubscriptions]);

  return {
    isChannelAudioPlaying,
    channelAudioSlug,
    isChannelAudioActive,
    handleSignal,
    playChannelChunk,
    resubscribeAll,
    subscribedChannels,
    isSubscribed,
    subscribe,
    unsubscribe,
    toggleSubscription,
    stopChannelAudio,
  };
}
