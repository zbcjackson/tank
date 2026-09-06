// Integration test for WsClient data routing: binary→parseAudio, text→parseJson, fragments.

#include "esp_stubs.cpp"
#include "freertos_stubs.cpp"
#include "net/WsProtocol.cpp"
#include "net/WsClient.cpp"

#include <gtest/gtest.h>
#include <cstring>
#include <string>
#include <vector>

#include "net/WsClient.h"
#include "net/WsProtocol.h"

// Stub WebSocket client functions (WsClient::connect/disconnect/send use these)
esp_websocket_client_handle_t esp_websocket_client_init(const esp_websocket_client_config_t*) { return (esp_websocket_client_handle_t)1; }
int esp_websocket_register_events(esp_websocket_client_handle_t, int32_t, esp_event_handler_t, void*) { return 0; }
int esp_websocket_client_start(esp_websocket_client_handle_t) { return 0; }

// Captured outbound frames — the negotiation tests assert on these.
static std::vector<std::string> g_sent_binary;
static std::vector<std::string> g_sent_text;
int esp_websocket_client_send_bin(esp_websocket_client_handle_t, const char* data, int len, TickType_t) {
    g_sent_binary.emplace_back(data, len);
    return len;
}
int esp_websocket_client_send_text(esp_websocket_client_handle_t, const char* data, int len, TickType_t) {
    g_sent_text.emplace_back(data, len);
    return len;
}
void esp_websocket_client_close(esp_websocket_client_handle_t, TickType_t) {}
void esp_websocket_client_destroy(esp_websocket_client_handle_t) {}

// Opus stubs — deterministic routing-level fakes. The real codec's quality
// and real-time cost are validated on hardware by the opus_bench suite.
struct OpusEncoder { int dummy; };
struct OpusDecoder { int dummy; };
static int g_fake_decode_samples = 320;
static int16_t g_fake_decode_first = -1234;
OpusEncoder* opus_encoder_create(int32_t, int, int, int* err) {
    *err = OPUS_OK;
    return new OpusEncoder{0};
}
void opus_encoder_destroy(OpusEncoder* enc) { delete enc; }
int opus_encoder_ctl(OpusEncoder*, int, ...) { return OPUS_OK; }
int opus_encode(OpusEncoder*, const opus_int16* pcm, int samples, unsigned char* out,
                opus_int32 cap) {
    if (cap < 8) return OPUS_BAD_ARG;
    out[0] = 0xAA; out[1] = 0x55;  // fake marker
    memcpy(out + 2, &samples, sizeof(samples));
    memcpy(out + 6, pcm, sizeof(opus_int16));
    return 8;
}
opus_int32 opus_encoder_get_size(int) { return 24544; }
int opus_encoder_init(OpusEncoder*, int32_t, int, int) { return OPUS_OK; }
opus_int32 opus_decoder_get_size(int) { return 17776; }
int opus_decoder_init(OpusDecoder*, int32_t, int) { return OPUS_OK; }
OpusDecoder* opus_decoder_create(int32_t, int, int* err) {
    *err = OPUS_OK;
    return new OpusDecoder{0};
}
void opus_decoder_destroy(OpusDecoder* dec) { delete dec; }
int opus_decode(OpusDecoder*, const unsigned char* data, opus_int32 len, opus_int16* pcm,
                int frame_cap, int) {
    if (len < 8 || frame_cap < g_fake_decode_samples) return OPUS_BAD_ARG;
    for (int i = 0; i < g_fake_decode_samples; i++) pcm[i] = g_fake_decode_first;
    return g_fake_decode_samples;
}

class WsRoutingTest : public ::testing::Test {
protected:
    void SetUp() override {
        ws_.init("localhost", 8000, "test_session");
        audio_calls_.clear();
        message_calls_.clear();
        g_sent_binary.clear();
        g_sent_text.clear();

        ws_.onAudio([this](const int16_t* pcm, size_t samples, uint32_t rate) {
            AudioCall call;
            call.samples = samples;
            call.sample_rate = rate;
            if (samples > 0 && pcm) {
                call.first_sample = pcm[0];
            }
            audio_calls_.push_back(call);
        });

        ws_.onMessage([this](const WsMessage& msg) {
            message_calls_.push_back(msg);
        });
    }

    // Simulate a single-event WebSocket data delivery
    void deliverData(uint8_t op_code, const void* data, int data_len) {
        esp_websocket_event_data_t event = {};
        event.op_code = op_code;
        event.data_ptr = (const char*)data;
        event.data_len = data_len;
        event.payload_len = data_len;
        event.payload_offset = 0;
        ws_.handleData(&event);
    }

    // Friendship grants WsRoutingTest (not the gtest subclasses) access —
    // route private-state pokes through these fixture methods.
    void setConnected(bool v) { ws_.connected_ = v; }
    void fireConnected() {
        esp_websocket_event_data_t ev = {};
        WsClient::eventHandler(&ws_, nullptr, WEBSOCKET_EVENT_CONNECTED, &ev);
    }
    void fireDisconnected() {
        esp_websocket_event_data_t ev = {};
        WsClient::eventHandler(&ws_, nullptr, WEBSOCKET_EVENT_DISCONNECTED, &ev);
    }

    // Simulate fragmented delivery (multiple events for one payload)
    void deliverFragmented(uint8_t op_code, const void* data, int total_len, int chunk_size) {
        const uint8_t* ptr = (const uint8_t*)data;
        int offset = 0;
        while (offset < total_len) {
            int this_chunk = std::min(chunk_size, total_len - offset);
            esp_websocket_event_data_t event = {};
            event.op_code = op_code;
            event.data_ptr = (const char*)(ptr + offset);
            event.data_len = this_chunk;
            event.payload_len = total_len;
            event.payload_offset = offset;
            ws_.handleData(&event);
            offset += this_chunk;
        }
    }

    struct AudioCall {
        size_t samples = 0;
        uint32_t sample_rate = 0;
        int16_t first_sample = 0;
    };

    WsClient ws_;
    std::vector<AudioCall> audio_calls_;
    std::vector<WsMessage> message_calls_;
};

TEST_F(WsRoutingTest, BinaryFrameRoutedToAudioCallback) {
    // Build a valid audio frame: 8-byte header + 4 bytes PCM (2 samples)
    uint8_t frame[12] = {};
    frame[0] = 0x4B; frame[1] = 0x54;  // magic
    frame[2] = 0x80; frame[3] = 0x3E; frame[4] = 0x00; frame[5] = 0x00;  // 16000
    frame[6] = 0x01; frame[7] = 0x00;  // 1 channel
    // PCM: sample 0 = 0x0100 = 256, sample 1 = 0x0200 = 512
    frame[8] = 0x00; frame[9] = 0x01;
    frame[10] = 0x00; frame[11] = 0x02;

    deliverData(0x02, frame, sizeof(frame));

    ASSERT_EQ(audio_calls_.size(), 1u);
    EXPECT_EQ(audio_calls_[0].samples, 2u);
    EXPECT_EQ(audio_calls_[0].sample_rate, 16000u);
    EXPECT_EQ(audio_calls_[0].first_sample, 256);
    EXPECT_EQ(message_calls_.size(), 0u);
}

TEST_F(WsRoutingTest, TextFrameRoutedToMessageCallback) {
    const char* json = R"({"type":"signal","content":"ready"})";
    deliverData(0x01, json, strlen(json));

    ASSERT_EQ(message_calls_.size(), 1u);
    EXPECT_STREQ(message_calls_[0].type, "signal");
    EXPECT_STREQ(message_calls_[0].content, "ready");
    EXPECT_EQ(audio_calls_.size(), 0u);
}

TEST_F(WsRoutingTest, InvalidBinaryFrameNotRouted) {
    // Wrong magic
    uint8_t frame[8] = {0x00, 0x00, 0x80, 0x3E, 0x00, 0x00, 0x01, 0x00};
    deliverData(0x02, frame, sizeof(frame));

    EXPECT_EQ(audio_calls_.size(), 0u);
}

TEST_F(WsRoutingTest, MalformedJsonNotRouted) {
    const char* bad = "not json {{{";
    deliverData(0x01, bad, strlen(bad));

    EXPECT_EQ(message_calls_.size(), 0u);
}

TEST_F(WsRoutingTest, FragmentedBinaryReassembled) {
    // 8-byte header + 8 bytes PCM = 16 total, delivered in 6-byte chunks
    uint8_t frame[16] = {};
    frame[0] = 0x4B; frame[1] = 0x54;  // magic
    frame[2] = 0x80; frame[3] = 0x3E; frame[4] = 0x00; frame[5] = 0x00;  // 16000
    frame[6] = 0x01; frame[7] = 0x00;  // 1 channel
    // 4 PCM samples
    frame[8] = 0x01; frame[9] = 0x00;   // 1
    frame[10] = 0x02; frame[11] = 0x00; // 2
    frame[12] = 0x03; frame[13] = 0x00; // 3
    frame[14] = 0x04; frame[15] = 0x00; // 4

    deliverFragmented(0x02, frame, 16, 6);

    ASSERT_EQ(audio_calls_.size(), 1u);
    EXPECT_EQ(audio_calls_[0].samples, 4u);
    EXPECT_EQ(audio_calls_[0].sample_rate, 16000u);
    EXPECT_EQ(audio_calls_[0].first_sample, 1);
}

TEST_F(WsRoutingTest, FragmentedTextReassembled) {
    const char* json = R"({"type":"text","content":"Hello world from fragmented frame","msg_id":"frag1"})";
    int len = strlen(json);

    deliverFragmented(0x01, json, len, 20);  // 20-byte chunks

    ASSERT_EQ(message_calls_.size(), 1u);
    EXPECT_STREQ(message_calls_[0].type, "text");
    EXPECT_STREQ(message_calls_[0].content, "Hello world from fragmented frame");
    EXPECT_STREQ(message_calls_[0].msg_id, "frag1");
}

TEST_F(WsRoutingTest, MultipleFramesIndependent) {
    const char* json1 = R"({"type":"signal","content":"processing_started"})";
    const char* json2 = R"({"type":"text","content":"Hi","msg_id":"m1"})";

    deliverData(0x01, json1, strlen(json1));
    deliverData(0x01, json2, strlen(json2));

    ASSERT_EQ(message_calls_.size(), 2u);
    EXPECT_STREQ(message_calls_[0].content, "processing_started");
    EXPECT_STREQ(message_calls_[1].content, "Hi");
}

TEST_F(WsRoutingTest, ShortBinaryFrameRejected) {
    // Only 4 bytes — too short for header
    uint8_t frame[4] = {0x4B, 0x54, 0x80, 0x3E};
    deliverData(0x02, frame, sizeof(frame));

    EXPECT_EQ(audio_calls_.size(), 0u);
}

// ---------------------------------------------------------------------------
// Opus negotiation (P1-2 Step 5)
// ---------------------------------------------------------------------------

TEST_F(WsRoutingTest, ReadyAdvertisingOpusSendsDeclaration) {
    ws_.connect();  // allocate the (stubbed) client handle
    setConnected(true);
    const char* ready =
        R"({"type":"signal","content":"ready","metadata":{)"
        R"("protocol_version":"0.3.0","protocol_features":["config","opus"]}})";
    deliverData(0x01, ready, strlen(ready));

    ASSERT_EQ(g_sent_text.size(), 1u);
    EXPECT_NE(g_sent_text[0].find("\"enable\":[\"opus\"]"), std::string::npos);

    // Uplink stays raw until the ack arrives.
    int16_t pcm[320] = {};
    pcm[0] = 999;
    ws_.sendAudio(pcm, 320);
    ASSERT_EQ(g_sent_binary.size(), 1u);
    EXPECT_EQ(g_sent_binary[0].size(), 640u);  // raw 320 samples
    EXPECT_EQ(audio_calls_.size(), 0u);
}

TEST_F(WsRoutingTest, ReadyWithoutOpusSendsNothing) {
    setConnected(true);
    const char* ready =
        R"({"type":"signal","content":"ready","metadata":{"protocol_features":["config"]}})";
    deliverData(0x01, ready, strlen(ready));

    EXPECT_EQ(g_sent_text.size(), 0u);
}

TEST_F(WsRoutingTest, DeclarationSentOncePerConnection) {
    ws_.connect();
    setConnected(true);
    const char* ready =
        R"({"type":"signal","content":"ready","metadata":{"protocol_features":["opus"]}})";
    deliverData(0x01, ready, strlen(ready));
    deliverData(0x01, ready, strlen(ready));

    EXPECT_EQ(g_sent_text.size(), 1u);
}

TEST_F(WsRoutingTest, AckSwitchesBothDirectionsToOpus) {
    ws_.connect();
    setConnected(true);
    const char* ready =
        R"({"type":"signal","content":"ready","metadata":{"protocol_features":["opus"]}})";
    deliverData(0x01, ready, strlen(ready));
    const char* ack =
        R"({"type":"signal","content":"capabilities","metadata":{"enabled":["opus"],)"
        R"("opus":{"uplink":{"sample_rate":16000,"frame_ms":20,"bitrate":32000}}}})";
    deliverData(0x01, ack, strlen(ack));

    // Uplink: one fake packet per 20 ms frame, not the raw PCM.
    int16_t pcm[320] = {};
    pcm[0] = 4321;
    ws_.sendAudio(pcm, 320);
    ASSERT_EQ(g_sent_binary.size(), 1u);
    ASSERT_EQ(g_sent_binary[0].size(), 8u);  // stub encode emits 8 bytes
    EXPECT_EQ((uint8_t)g_sent_binary[0][0], 0xAA);
    EXPECT_EQ((uint8_t)g_sent_binary[0][1], 0x55);
    int embedded_samples = 0;
    memcpy(&embedded_samples, g_sent_binary[0].data() + 2, sizeof(embedded_samples));
    EXPECT_EQ(embedded_samples, 320);

    // Downlink: opus packets decode to PCM at the speaker rate.
    const uint8_t pkt[8] = {0xAA, 0x55, 1, 2, 3, 4, 5, 6};
    deliverData(0x02, pkt, sizeof(pkt));
    ASSERT_EQ(audio_calls_.size(), 1u);
    EXPECT_EQ(audio_calls_[0].samples, 320u);
    EXPECT_EQ(audio_calls_[0].sample_rate, 16000u);
    EXPECT_EQ(audio_calls_[0].first_sample, -1234);
}

TEST_F(WsRoutingTest, DisconnectResetsNegotiation) {
    ws_.connect();
    setConnected(true);
    const char* ready =
        R"({"type":"signal","content":"ready","metadata":{"protocol_features":["opus"]}})";
    deliverData(0x01, ready, strlen(ready));
    const char* ack =
        R"({"type":"signal","content":"capabilities","metadata":{"enabled":["opus"]}})";
    deliverData(0x01, ack, strlen(ack));
    ASSERT_EQ(g_sent_text.size(), 1u);

    // Disconnect wipes the negotiated state.
    fireDisconnected();
    EXPECT_FALSE(ws_.isConnected());

    // Fresh connection: ready must produce a NEW declaration.
    fireConnected();
    setConnected(true);
    deliverData(0x01, ready, strlen(ready));
    ASSERT_EQ(g_sent_text.size(), 2u);

    // And it re-negotiates on the ack.
    deliverData(0x01, ack, strlen(ack));
    int16_t pcm[320] = {};
    ws_.sendAudio(pcm, 320);
    ASSERT_EQ(g_sent_binary.size(), 1u);
    EXPECT_EQ(g_sent_binary[0].size(), 8u);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
