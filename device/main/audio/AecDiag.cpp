#include "AecDiag.h"

#include <cmath>

// Definition of the JTAG-readable diagnostics block. Placed in .bss so the
// debugger can resolve `g_aec_diag` by name at a fixed address.
AecDiag g_aec_diag = {};

// Aggregate over ~a quarter second so a halted read reflects steady state rather
// than a single 20ms frame. 16kHz / 4 ≈ 4000 samples.
static constexpr int WINDOW_SAMPLES = 4000;

namespace {
// Input (raw mic/ref) accumulators.
int64_t in_mic_sq = 0, in_ref_sq = 0;
int32_t in_mic_peak = 0, in_ref_peak = 0;
int in_count = 0;

// Output (post-AEC) accumulators.
int64_t out_sq = 0;
int32_t out_pk = 0;
int out_count = 0;

// Most recent input mic RMS, kept to pair with the next output window for ERLE.
double last_mic_rms = 0.0;

inline int32_t iabs16(int16_t v) { return v < 0 ? -(int32_t)v : (int32_t)v; }
}  // namespace

void aecDiagInput(const int16_t* interleaved, int samples_per_channel, int stride,
                  int mic_ch, int ref_ch) {
    for (int i = 0; i < samples_per_channel; i++) {
        int16_t m = interleaved[i * stride + mic_ch];
        int16_t r = interleaved[i * stride + ref_ch];
        int32_t ma = iabs16(m), ra = iabs16(r);
        if (ma > in_mic_peak) in_mic_peak = ma;
        if (ra > in_ref_peak) in_ref_peak = ra;
        in_mic_sq += (int64_t)m * m;
        in_ref_sq += (int64_t)r * r;
        in_count++;
    }

    if (in_count >= WINDOW_SAMPLES) {
        double mic_rms = std::sqrt((double)in_mic_sq / in_count);
        double ref_rms = std::sqrt((double)in_ref_sq / in_count);
        g_aec_diag.mic_peak = in_mic_peak;
        g_aec_diag.ref_peak = in_ref_peak;
        g_aec_diag.mic_rms = (int32_t)mic_rms;
        g_aec_diag.ref_rms = (int32_t)ref_rms;
        g_aec_diag.input_windows++;
        last_mic_rms = mic_rms;

        // Max-hold: capture the loudest moment across the session.
        if (in_mic_peak > g_aec_diag.mic_peak_hold) g_aec_diag.mic_peak_hold = in_mic_peak;
        if (in_ref_peak > g_aec_diag.ref_peak_hold) g_aec_diag.ref_peak_hold = in_ref_peak;
        if ((int32_t)mic_rms > g_aec_diag.mic_rms_max) g_aec_diag.mic_rms_max = (int32_t)mic_rms;
        if ((int32_t)ref_rms > g_aec_diag.ref_rms_max) g_aec_diag.ref_rms_max = (int32_t)ref_rms;

        in_mic_sq = in_ref_sq = 0;
        in_mic_peak = in_ref_peak = 0;
        in_count = 0;
    }
}

void aecDiagOutput(const int16_t* out, int samples) {
    for (int i = 0; i < samples; i++) {
        int16_t s = out[i];
        int32_t a = iabs16(s);
        if (a > out_pk) out_pk = a;
        out_sq += (int64_t)s * s;
        out_count++;
    }

    if (out_count >= WINDOW_SAMPLES) {
        double out_rms = std::sqrt((double)out_sq / out_count);
        g_aec_diag.out_peak = out_pk;
        g_aec_diag.out_rms = (int32_t)out_rms;
        g_aec_diag.output_windows++;

        // ERLE: how much the mic-path power dropped after AEC. Guard against
        // divide-by-zero on silence; only meaningful when there is echo to
        // cancel (i.e. mic_rms was non-trivial in the paired input window).
        if (out_rms > 1.0 && last_mic_rms > 1.0) {
            float erle = (float)(20.0 * std::log10(last_mic_rms / out_rms));
            g_aec_diag.erle_db = erle;
            if (erle > g_aec_diag.erle_db_best) g_aec_diag.erle_db_best = erle;
        }

        out_sq = 0;
        out_pk = 0;
        out_count = 0;
    }
}
