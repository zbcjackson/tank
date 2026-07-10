#pragma once

#include <cstdint>

/// JTAG-readable AEC diagnostics. These globals are updated over a rolling
/// window as audio flows, so a debugger can halt the running device and read
/// them by name to answer two questions without needing serial logs:
///
///   1. "Is the MIC3 echo reference wired?"  → while the speaker plays, does
///      `ref_peak` / `ref_rms` rise with playback, or stay at noise floor?
///
///   2. "Does AEC cancel the echo?"  → measured while the speaker plays and the
///      room is quiet (echo-only): `erle_db` is the Echo Return Loss
///      Enhancement = 10·log10(mic_power / afe_output_power). ~0 dB means AEC
///      is doing nothing; 10–30 dB means it is removing the echo.
///
/// Read from gdb:  print g_aec_diag
struct AecDiag {
    // Raw capture channels (pre-AFE), latched per window.
    volatile int32_t mic_peak;    // peak |sample| on the mic channel (slot 0)
    volatile int32_t ref_peak;    // peak |sample| on the ref channel (slot 2 / MIC3)
    volatile int32_t mic_rms;     // RMS of the mic channel
    volatile int32_t ref_rms;     // RMS of the ref channel

    // AFE output (post-AEC), latched per window.
    volatile int32_t out_peak;    // peak |sample| on the echo-cancelled output
    volatile int32_t out_rms;     // RMS of the echo-cancelled output

    // Echo cancellation figure of merit.
    volatile float erle_db;       // 20·log10(mic_rms / out_rms); >0 => echo removed

    volatile uint32_t input_windows;   // count of input windows aggregated
    volatile uint32_t output_windows;  // count of output windows aggregated
    volatile bool tone_playing;        // true while the boot test tone is active

    // Max-hold across the whole session (never reset), so a JTAG read at any
    // time captures whatever the loudest moment was — timing-independent.
    volatile int32_t mic_peak_hold;    // loudest mic sample ever seen
    volatile int32_t ref_peak_hold;    // loudest ref (MIC3) sample ever seen
    volatile int32_t mic_rms_max;      // largest mic RMS window
    volatile int32_t ref_rms_max;      // largest ref RMS window
    volatile float erle_db_best;       // best (largest) ERLE seen during echo
};

extern AecDiag g_aec_diag;

/// Feed one window's worth of raw interleaved [mic, ref] samples (the capture
/// frame). Accumulates power/peak and latches into g_aec_diag once the window
/// fills. `stride` is the channel count (mic + ref).
void aecDiagInput(const int16_t* interleaved, int samples_per_channel, int stride,
                  int mic_ch, int ref_ch);

/// Feed one AFE output frame (single channel, echo-cancelled). Latches out_*
/// and recomputes erle_db against the most recent input window.
void aecDiagOutput(const int16_t* out, int samples);
