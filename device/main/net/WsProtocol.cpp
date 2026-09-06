// Protocol parsing logic extracted from WsClient.
// Pure functions — no ESP-IDF dependency except cJSON (portable C library).

#include "WsProtocol.h"
#include "WsClient.h"
#include "config.h"
#include "cJSON.h"

#include <cstdlib>
#include <cstring>

bool parseAudioFrameHeader(const uint8_t* data, int len, AudioFrameHeader* out) {
    if (len < AUDIO_FRAME_HEADER_SIZE) {
        return false;
    }

    uint16_t magic = data[0] | (data[1] << 8);
    if (magic != AUDIO_FRAME_MAGIC) {
        return false;
    }

    out->magic = magic;
    out->sample_rate = data[2] | (data[3] << 8) | (data[4] << 16) | (data[5] << 24);
    out->channels = data[6] | (data[7] << 8);
    return true;
}

bool parseWsJsonMessage(const char* data, int len, WsMessage* out) {
    // Null-terminate for cJSON (data may not be terminated)
    char* buf = (char*)malloc(len + 1);
    if (!buf) return false;
    memcpy(buf, data, len);
    buf[len] = '\0';

    cJSON* root = cJSON_Parse(buf);
    if (!root) {
        free(buf);
        return false;
    }

    memset(out, 0, sizeof(WsMessage));

    cJSON* type = cJSON_GetObjectItem(root, "type");
    if (type && cJSON_IsString(type)) {
        strncpy(out->type, type->valuestring, sizeof(out->type) - 1);
    }

    cJSON* content = cJSON_GetObjectItem(root, "content");
    if (content && cJSON_IsString(content)) {
        strncpy(out->content, content->valuestring, sizeof(out->content) - 1);
    }

    cJSON* msg_id = cJSON_GetObjectItem(root, "msg_id");
    if (msg_id && cJSON_IsString(msg_id)) {
        strncpy(out->msg_id, msg_id->valuestring, sizeof(out->msg_id) - 1);
    }

    cJSON* is_user = cJSON_GetObjectItem(root, "is_user");
    out->is_user = is_user && cJSON_IsTrue(is_user);

    cJSON* is_final = cJSON_GetObjectItem(root, "is_final");
    out->is_final = is_final && cJSON_IsTrue(is_final);

    cJSON_Delete(root);
    free(buf);
    return true;
}
