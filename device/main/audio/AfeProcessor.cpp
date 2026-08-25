#include "AfeProcessor.h"
#include "config.h"

#include "esp_log.h"
#include "esp_afe_sr_models.h"
#include "esp_afe_sr_iface.h"
#include "esp_afe_config.h"
#include "model_path.h"

static const char* TAG = "AfeProcessor";

bool AfeProcessor::init() {
    // Load the speech models flashed to the "model" partition (same partition
    // WakeWordDetector used). The AFE resolves its WakeNet model by name from
    // this list.
    auto* models = esp_srmodel_init("model");
    models_ = models;
    if (!models) {
        ESP_LOGE(TAG, "esp_srmodel_init failed — no model partition?");
        return false;
    }

    char* wn_model = esp_srmodel_filter(models, ESP_WN_PREFIX, NULL);
    if (!wn_model) {
        ESP_LOGE(TAG, "No WakeNet model found in partition");
        return false;
    }

    afe_config_t cfg = AFE_CONFIG_DEFAULT();

    // CoreS3 topology: one physical mic (ES7210 MIC1) + one hardware echo
    // reference (MIC3). The S3 default assumes 2 mic + 1 ref, so override the
    // channel counts to match what AudioCapture feeds.
    cfg.pcm_config.total_ch_num = CONFIG_AFE_TOTAL_CH;
    cfg.pcm_config.mic_num = CONFIG_AFE_MIC_NUM;
    cfg.pcm_config.ref_num = CONFIG_AFE_REF_NUM;
    cfg.pcm_config.sample_rate = CONFIG_MIC_SAMPLE_RATE;

    cfg.aec_init = true;
    cfg.se_init = false;   // MASE speech-enhancement needs a ≥2-mic array; we have 1
    cfg.vad_init = true;
    cfg.wakenet_init = true;
    cfg.wakenet_model_name = wn_model;
    cfg.wakenet_mode = DET_MODE_90;   // single-mic detection (not the 2CH default)

    cfg.afe_mode = SR_MODE_LOW_COST;
    cfg.afe_perferred_core = CONFIG_AUDIO_TASK_CORE;   // keep AFE work off Core 1 (net/UI)
    cfg.afe_perferred_priority = 5;
    cfg.memory_alloc_mode = AFE_MEMORY_ALLOC_MORE_PSRAM;

    auto* iface = &ESP_AFE_SR_HANDLE;
    afe_iface_ = iface;

    auto* data = iface->create_from_config(&cfg);
    afe_data_ = data;
    if (!data) {
        ESP_LOGE(TAG, "AFE create_from_config failed");
        return false;
    }

    feed_chunk_samples_ = iface->get_feed_chunksize(data);
    feed_channels_ = iface->get_total_channel_num(data);
    if (feed_chunk_samples_ <= 0 || feed_channels_ <= 0) {
        ESP_LOGE(TAG, "Invalid AFE feed geometry: chunk=%d ch=%d",
                 feed_chunk_samples_, feed_channels_);
        iface->destroy(data);
        afe_data_ = nullptr;
        return false;
    }

    ESP_LOGI(TAG, "AFE ready: model=%s, feed chunk=%d samples/ch, channels=%d, AEC on",
             wn_model, feed_chunk_samples_, feed_channels_);
    return true;
}

void AfeProcessor::destroy() {
    auto* iface = static_cast<const esp_afe_sr_iface_t*>(afe_iface_);
    auto* data = static_cast<esp_afe_sr_data_t*>(afe_data_);
    if (iface && data) {
        iface->destroy(data);
    }
    afe_data_ = nullptr;
    if (models_) {
        esp_srmodel_deinit(static_cast<srmodel_list_t*>(models_));
        models_ = nullptr;
    }
}

bool AfeProcessor::feed(const int16_t* interleaved) {
    auto* iface = static_cast<const esp_afe_sr_iface_t*>(afe_iface_);
    auto* data = static_cast<esp_afe_sr_data_t*>(afe_data_);
    if (!iface || !data) return false;
    iface->feed(data, interleaved);
    return true;
}

AfeProcessor::FetchResult AfeProcessor::fetch() {
    FetchResult out;
    auto* iface = static_cast<const esp_afe_sr_iface_t*>(afe_iface_);
    auto* data = static_cast<esp_afe_sr_data_t*>(afe_data_);
    if (!iface || !data) return out;

    afe_fetch_result_t* res = iface->fetch(data);
    if (!res || res->ret_value == -1) {
        return out;
    }

    out.data = res->data;
    out.samples = res->data_size / (int)sizeof(int16_t);
    out.wake_detected = (res->wakeup_state == WAKENET_DETECTED);
    out.speech = (res->vad_state == AFE_VAD_SPEECH);
    out.valid = true;
    return out;
}

void AfeProcessor::enableAec(bool enable) {
    auto* iface = static_cast<const esp_afe_sr_iface_t*>(afe_iface_);
    auto* data = static_cast<esp_afe_sr_data_t*>(afe_data_);
    if (!iface || !data) return;
    if (enable) {
        iface->enable_aec(data);
    } else {
        iface->disable_aec(data);
    }
}
