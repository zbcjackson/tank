// Unit tests for WebSocket JSON message parsing.

#include "net/WsProtocol.cpp"

#include <gtest/gtest.h>
#include <cstring>
#include <string>

#include "golden_frames.h"
#include "net/WsProtocol.h"
#include "net/WsClient.h"

TEST(WsMessageParse, FullMessage) {
    const char* json = R"({"type":"text","content":"Hello world","msg_id":"abc123","is_user":false,"is_final":true})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "text");
    EXPECT_STREQ(msg.content, "Hello world");
    EXPECT_STREQ(msg.msg_id, "abc123");
    EXPECT_FALSE(msg.is_user);
    EXPECT_TRUE(msg.is_final);
}

TEST(WsMessageParse, SignalReady) {
    const char* json = R"({"type":"signal","content":"ready"})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "signal");
    EXPECT_STREQ(msg.content, "ready");
    EXPECT_FALSE(msg.is_user);
    EXPECT_FALSE(msg.is_final);
}

TEST(WsMessageParse, UserTranscript) {
    const char* json = R"({"type":"transcript","content":"how are you","is_user":true,"is_final":true})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "transcript");
    EXPECT_STREQ(msg.content, "how are you");
    EXPECT_TRUE(msg.is_user);
    EXPECT_TRUE(msg.is_final);
}

TEST(WsMessageParse, MissingOptionalFields) {
    const char* json = R"({"type":"transcript"})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "transcript");
    EXPECT_STREQ(msg.content, "");
    EXPECT_STREQ(msg.msg_id, "");
    EXPECT_FALSE(msg.is_user);
    EXPECT_FALSE(msg.is_final);
}

TEST(WsMessageParse, TruncatesLongContent) {
    // content field is char[512], so 600-char string should be truncated
    std::string long_content(600, 'A');
    std::string json = R"({"type":"text","content":")" + long_content + R"("})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json.c_str(), json.size(), &msg));
    EXPECT_EQ(strlen(msg.content), 511u);  // truncated to buffer size - 1
}

TEST(WsMessageParse, TruncatesLongType) {
    // type field is char[32]; the longest real protocol name is 29 chars and
    // must fit whole (golden frames assert this), so truncate only past 31.
    std::string long_type(40, 'x');
    std::string json = R"({"type":")" + long_type + R"("})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json.c_str(), json.size(), &msg));
    EXPECT_EQ(strlen(msg.type), 31u);
}

TEST(WsMessageParse, LongestProtocolTypeNameFitsWhole) {
    // "conversation_metadata_updated" is the longest MessageType value.
    const char* json = R"({"type":"conversation_metadata_updated"})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "conversation_metadata_updated");
}

TEST(WsMessageParse, MalformedJsonReturnsFalse) {
    const char* bad = "not json at all {{{";
    WsMessage msg = {};
    EXPECT_FALSE(parseWsJsonMessage(bad, strlen(bad), &msg));
}

TEST(WsMessageParse, EmptyJsonObject) {
    const char* json = "{}";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "");
    EXPECT_STREQ(msg.content, "");
}

TEST(WsMessageParse, NullContentField) {
    const char* json = R"({"type":"text","content":null})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "text");
    EXPECT_STREQ(msg.content, "");  // null treated as missing
}

TEST(WsMessageParse, NumericContentIgnored) {
    // content as number should be ignored (only string accepted)
    const char* json = R"({"type":"text","content":42})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.content, "");
}

TEST(WsMessageParse, UpdateMessage) {
    const char* json = R"({"type":"update","content":"thinking","msg_id":"msg_001","is_final":false})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, "update");
    EXPECT_STREQ(msg.content, "thinking");
    EXPECT_STREQ(msg.msg_id, "msg_001");
    EXPECT_FALSE(msg.is_final);
}

TEST(WsMessageParse, ZeroLengthInput) {
    WsMessage msg = {};
    EXPECT_FALSE(parseWsJsonMessage("", 0, &msg));
}

// ---------------------------------------------------------------------------
// Golden frames — real wire frames generated from the tank_protocol contract
// package (backend/contracts/tank_protocol). One test per outbound message
// type asserts the C++ parser against exactly what the Python server sends,
// including fields the parser ignores (speaker/session_id/metadata/nulls).
// ---------------------------------------------------------------------------

static void expectGolden(const char* json, const char* type, const char* content,
                         const char* msg_id, bool is_user, bool is_final) {
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json, strlen(json), &msg));
    EXPECT_STREQ(msg.type, type);
    EXPECT_STREQ(msg.content, content);
    EXPECT_STREQ(msg.msg_id, msg_id);
    EXPECT_EQ(msg.is_user, is_user);
    EXPECT_EQ(msg.is_final, is_final);
}

TEST(WsGoldenFrames, SignalReady) {
    expectGolden(TANK_GOLDEN_SIGNAL, "signal", "ready", "", false, false);
}

TEST(WsGoldenFrames, TranscriptUtf8) {
    expectGolden(TANK_GOLDEN_TRANSCRIPT, "transcript", "你好", "u_golden", true, true);
}

TEST(WsGoldenFrames, TextStreamDelta) {
    expectGolden(TANK_GOLDEN_TEXT, "text", "Hello", "m_golden", false, false);
}

TEST(WsGoldenFrames, UpdateTool) {
    expectGolden(TANK_GOLDEN_UPDATE, "update", "", "m_golden", false, false);
}

TEST(WsGoldenFrames, AttachmentCaption) {
    expectGolden(TANK_GOLDEN_ATTACHMENT, "attachment", "a photo", "m_golden", false, true);
}

TEST(WsGoldenFrames, ChannelNotification) {
    expectGolden(TANK_GOLDEN_CHANNEL_NOTIFICATION, "channel_notification", "", "", false, false);
}

TEST(WsGoldenFrames, ConversationMetadata) {
    expectGolden(TANK_GOLDEN_CONVERSATION_METADATA, "conversation_metadata_updated",
                 "", "", false, true);
}

TEST(WsGoldenFrames, ConfigHotConfig) {
    // P1-3: new inbound type — the device doesn't act on it, but the
    // parser must accept it whole (type fits, fields intact).
    expectGolden(TANK_GOLDEN_CONFIG, "config", "", "", false, false);
}

TEST(WsGoldenFrames, ContextInject) {
    expectGolden(TANK_GOLDEN_CONTEXT_INJECT, "context_inject",
                 "Note from retrieval: the user prefers metric units.",
                 "", false, false);
}

TEST(WsGoldenFrames, UnknownFieldTolerated) {
    // Evolution rule 2: unknown fields must be ignored, not rejected.
    expectGolden(TANK_GOLDEN_UNKNOWN_FIELD, "text", "future", "", false, false);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
