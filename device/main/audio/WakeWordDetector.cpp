#include "WakeWordDetector.h"

#include "esp_log.h"
#include "esp_wn_iface.h"
#include "esp_wn_models.h"
#include "model_path.h"

static const char* TAG = "WakeWord";

WakeWordDetector::~WakeWordDetector() {
    auto* iface = static_cast<const esp_wn_iface_t*>(iface_);
    auto* data = static_cast<model_iface_data_t*>(data_);
    if (iface && data) {
        iface->destroy(data);
    }
    delete chunker_;
    if (models_) {
        esp_srmodel_deinit(static_cast<srmodel_list_t*>(models_));
    }
}

bool WakeWordDetector::init() {
    // Load all speech models flashed to the "model" partition.
    auto* models = esp_srmodel_init("model");
    models_ = models;
    if (!models) {
        ESP_LOGE(TAG, "esp_srmodel_init failed — no model partition?");
        return false;
    }

    // Pick the first WakeNet model (prefix "wn"). With a single stock word
    // flashed ("Hi ESP"), this resolves to wn9_hiesp.
    char* model_name = esp_srmodel_filter(models, ESP_WN_PREFIX, NULL);
    if (!model_name) {
        ESP_LOGE(TAG, "No WakeNet model found in partition");
        return false;
    }

    auto* iface = esp_wn_handle_from_name(model_name);
    iface_ = iface;
    if (!iface) {
        ESP_LOGE(TAG, "No WakeNet interface for model %s", model_name);
        return false;
    }

    // Single-mic board → normal detection mode.
    auto* data = iface->create(model_name, DET_MODE_90);
    data_ = data;
    if (!data) {
        ESP_LOGE(TAG, "WakeNet create failed for %s", model_name);
        return false;
    }

    chunk_samples_ = iface->get_samp_chunksize(data);
    if (chunk_samples_ <= 0) {
        ESP_LOGE(TAG, "Invalid WakeNet chunk size %d", chunk_samples_);
        iface->destroy(data);
        data_ = nullptr;
        return false;
    }

    chunker_ = new FrameChunker(static_cast<size_t>(chunk_samples_));
    ESP_LOGI(TAG, "WakeNet ready: model=%s, chunk=%d samples", model_name, chunk_samples_);
    return true;
}

bool WakeWordDetector::feed(const int16_t* samples, size_t count) {
    auto* iface = static_cast<const esp_wn_iface_t*>(iface_);
    auto* data = static_cast<model_iface_data_t*>(data_);
    if (!iface || !data || !chunker_) return false;

    chunker_->push(samples, count);

    bool detected = false;
    // WakeNet mutates its internal buffer, so a scratch chunk is required.
    int16_t* chunk = new int16_t[chunk_samples_];
    while (chunker_->pop(chunk)) {
        wakenet_state_t st = iface->detect(data, chunk);
        if (st == WAKENET_DETECTED) {
            detected = true;
            // Drain remaining buffered chunks to avoid a stale re-trigger on
            // the next feed, but stop detecting once we've fired this frame.
            chunker_->reset();
            break;
        }
    }
    delete[] chunk;
    return detected;
}

void WakeWordDetector::reset() {
    if (chunker_) chunker_->reset();
}
