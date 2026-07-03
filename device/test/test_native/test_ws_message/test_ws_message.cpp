// Unit tests for WebSocket JSON message parsing.

#include "net/WsProtocol.cpp"

#include <gtest/gtest.h>
#include <cstring>
#include <string>

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
    // type field is char[20], so 30-char type should be truncated
    std::string long_type(30, 'x');
    std::string json = R"({"type":")" + long_type + R"("})";
    WsMessage msg = {};
    ASSERT_TRUE(parseWsJsonMessage(json.c_str(), json.size(), &msg));
    EXPECT_EQ(strlen(msg.type), 19u);
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

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
