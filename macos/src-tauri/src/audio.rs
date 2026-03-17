use std::sync::Arc;

use nnnoiseless::DenoiseState;
use rubato::{FftFixedInOut, Resampler};
use sys_voice::{AecConfig, CaptureHandle, Channels, PlaybackStreamHandle};
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::Mutex;

const CAPTURE_SAMPLE_RATE: u32 = 48000;
const OUTPUT_SAMPLE_RATE: u32 = 16000;
const PLAYBACK_SAMPLE_RATE: u32 = 24000;

/// Shared audio state managed by Tauri.
pub struct AudioState {
    inner: Mutex<Option<AudioInner>>,
}

struct AudioInner {
    /// Shared with the capture loop task — kept alive via Arc.
    capture_handle: Arc<CaptureHandle>,
    playback_handle: Option<PlaybackStreamHandle>,
}

impl AudioState {
    pub fn new() -> Self {
        Self {
            inner: Mutex::new(None),
        }
    }
}

/// Start native audio capture with AEC + ANC.
/// Emits `audio-capture` events with raw Int16 PCM bytes at 16kHz.
#[tauri::command]
pub async fn start_audio_capture(app: AppHandle) -> Result<(), String> {
    let state = app.state::<AudioState>();
    let mut guard = state.inner.lock().await;

    if guard.is_some() {
        return Err("Audio capture already running".into());
    }

    let config = AecConfig {
        sample_rate: CAPTURE_SAMPLE_RATE,
        channels: Channels::Mono,
    };

    let capture_handle = CaptureHandle::new(config)
        .map_err(|e| format!("Failed to start capture: {e}"))?;

    let capture_handle = Arc::new(capture_handle);

    let playback_handle = capture_handle
        .start_playback_stream(PLAYBACK_SAMPLE_RATE)
        .map_err(|e| format!("Failed to start playback stream: {e}"))?;

    *guard = Some(AudioInner {
        capture_handle: Arc::clone(&capture_handle),
        playback_handle: Some(playback_handle),
    });
    drop(guard);

    // Spawn the capture processing loop with its own Arc ref
    let app_clone = app.clone();
    tokio::spawn(async move {
        if let Err(e) = capture_loop(capture_handle, app_clone).await {
            log::error!("Capture loop error: {e}");
        }
    });

    Ok(())
}

async fn capture_loop(
    capture_handle: Arc<CaptureHandle>,
    app: AppHandle,
) -> Result<(), String> {
    // Initialize nnnoiseless denoiser
    let mut denoise = DenoiseState::new();
    let mut denoise_input = [0.0f32; DenoiseState::FRAME_SIZE];
    let mut denoise_output = [0.0f32; DenoiseState::FRAME_SIZE];
    let mut first_frame = true;

    // Initialize rubato resampler: 48kHz → 16kHz, mono
    let mut resampler = FftFixedInOut::<f32>::new(
        CAPTURE_SAMPLE_RATE as usize,
        OUTPUT_SAMPLE_RATE as usize,
        DenoiseState::FRAME_SIZE, // 480 samples = 10ms at 48kHz
        1,                        // mono
    )
    .map_err(|e| format!("Failed to create resampler: {e}"))?;

    // Buffer for accumulating samples until we have a full frame
    let mut sample_buf: Vec<f32> = Vec::with_capacity(DenoiseState::FRAME_SIZE * 2);

    loop {
        // recv() returns None when the CaptureHandle is dropped
        let samples = match capture_handle.recv().await {
            Some(Ok(s)) => s,
            Some(Err(e)) => {
                log::error!("Capture recv error: {e}");
                let _ = app.emit("audio-error", format!("Capture error: {e}"));
                break;
            }
            None => break,
        };

        sample_buf.extend_from_slice(&samples);

        // Process complete 480-sample frames
        while sample_buf.len() >= DenoiseState::FRAME_SIZE {
            let frame: Vec<f32> = sample_buf.drain(..DenoiseState::FRAME_SIZE).collect();

            // Scale f32 [-1.0, 1.0] → [-32768.0, 32767.0] for nnnoiseless
            for (i, &s) in frame.iter().enumerate() {
                denoise_input[i] = s * 32768.0;
            }

            denoise.process_frame(&mut denoise_output, &denoise_input);

            if first_frame {
                first_frame = false;
                continue; // Discard first frame (fade-in artifacts)
            }

            // Scale back to [-1.0, 1.0]
            let denoised: Vec<f32> = denoise_output
                .iter()
                .map(|&s| s / 32768.0)
                .collect();

            // Resample 48kHz → 16kHz
            let resampled = resampler
                .process(&[denoised], None)
                .map_err(|e| format!("Resample error: {e}"))?;

            if resampled[0].is_empty() {
                continue;
            }

            // Convert f32 → i16
            let int16_samples: Vec<i16> = resampled[0]
                .iter()
                .map(|&s| (s.clamp(-1.0, 1.0) * 32767.0) as i16)
                .collect();

            // Emit as raw little-endian bytes
            let bytes: Vec<u8> = int16_samples
                .iter()
                .flat_map(|s| s.to_le_bytes())
                .collect();

            if let Err(e) = app.emit("audio-capture", bytes) {
                log::error!("Failed to emit audio-capture: {e}");
                break;
            }
        }
    }

    Ok(())
}

/// Play TTS audio through the native playback stream (for AEC reference).
/// Expects raw Int16 PCM bytes at 24kHz.
#[tauri::command]
pub async fn play_audio(app: AppHandle, samples: Vec<u8>) -> Result<(), String> {
    let state = app.state::<AudioState>();
    let guard = state.inner.lock().await;

    let inner = guard.as_ref().ok_or("Audio not started")?;
    let playback = inner
        .playback_handle
        .as_ref()
        .ok_or("Playback stream not available")?;

    if !samples.len().is_multiple_of(2) {
        return Err("Invalid audio data length".into());
    }

    let float_samples: Vec<f32> = samples
        .chunks_exact(2)
        .map(|chunk| {
            let sample = i16::from_le_bytes([chunk[0], chunk[1]]);
            sample as f32 / 32768.0
        })
        .collect();

    playback
        .send(float_samples)
        .map_err(|e| format!("Playback send error: {e}"))?;

    Ok(())
}

/// Stop playback and recreate the stream (for interruption).
#[tauri::command]
pub async fn stop_playback(app: AppHandle) -> Result<(), String> {
    let state = app.state::<AudioState>();
    let mut guard = state.inner.lock().await;

    let inner = guard.as_mut().ok_or("Audio not started")?;

    // Drop current playback handle
    inner.playback_handle.take();

    // Create a new one
    let new_handle = inner
        .capture_handle
        .start_playback_stream(PLAYBACK_SAMPLE_RATE)
        .map_err(|e| format!("Failed to restart playback: {e}"))?;

    inner.playback_handle = Some(new_handle);

    Ok(())
}

/// Stop all audio capture and playback.
#[tauri::command]
pub async fn stop_audio_capture(app: AppHandle) -> Result<(), String> {
    let state = app.state::<AudioState>();
    let mut guard = state.inner.lock().await;

    // Dropping AudioInner drops the Arc<CaptureHandle> (our ref).
    // The capture loop holds another Arc ref — recv() will return None
    // once the underlying stream closes, ending the loop naturally.
    *guard = None;

    Ok(())
}
