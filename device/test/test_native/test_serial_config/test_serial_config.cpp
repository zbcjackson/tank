// Unit tests for SerialConfig AT command parsing.

// Include source files needed for this test
#include "esp_stubs.cpp"
#include "nvs_stubs.cpp"
#include "freertos_stubs.cpp"

// NvsSettings source — rename its static TAG to avoid collision with SerialConfig
#define TAG NVS_TAG
#include "settings/NvsSettings.cpp"
#undef TAG

// SerialConfig source
#define TAG SERIAL_TAG
#include "settings/SerialConfig.cpp"
#undef TAG

#include <gtest/gtest.h>
#include <cstring>

#include "settings/SerialConfig.h"
#include "settings/NvsSettings.h"
#include "nvs_stubs.h"

class SerialConfigTest : public ::testing::Test {
protected:
    void SetUp() override {
        nvs_stub_reset();
        nvs_.init();
        config_.init(&nvs_, nullptr, nullptr);
    }

    NvsSettings nvs_;
    SerialConfig config_;

    // Helper: call processLine with a mutable copy of the string
    void process(const char* line) {
        char buf[256];
        strncpy(buf, line, sizeof(buf) - 1);
        buf[sizeof(buf) - 1] = '\0';
        config_.processLine(buf);
    }
};

TEST_F(SerialConfigTest, SetSSID) {
    process("AT+SSID=MyNetwork");
    char buf[64] = {};
    ASSERT_TRUE(nvs_.getWifiSSID(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "MyNetwork");
}

TEST_F(SerialConfigTest, SetPassword) {
    process("AT+PASS=secret123");
    char buf[64] = {};
    ASSERT_TRUE(nvs_.getWifiPassword(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "secret123");
}

TEST_F(SerialConfigTest, SetHost) {
    process("AT+HOST=192.168.1.200");
    char buf[64] = {};
    ASSERT_TRUE(nvs_.getBackendHost(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "192.168.1.200");
}

TEST_F(SerialConfigTest, SetPort) {
    process("AT+PORT=9000");
    EXPECT_EQ(nvs_.getBackendPort(), 9000);
}

TEST_F(SerialConfigTest, InvalidPortZero) {
    nvs_.setBackendPort(8000);
    process("AT+PORT=0");
    EXPECT_EQ(nvs_.getBackendPort(), 8000);  // unchanged
}

TEST_F(SerialConfigTest, InvalidPortNonNumeric) {
    nvs_.setBackendPort(8000);
    process("AT+PORT=abc");
    EXPECT_EQ(nvs_.getBackendPort(), 8000);  // unchanged (atoi returns 0)
}

TEST_F(SerialConfigTest, UnknownKeyIgnored) {
    process("AT+UNKNOWN=value");
    char buf[64] = {};
    EXPECT_FALSE(nvs_.getWifiSSID(buf, sizeof(buf)));
}

TEST_F(SerialConfigTest, NonATCommandIgnored) {
    process("hello world");
    char buf[64] = {};
    EXPECT_FALSE(nvs_.getWifiSSID(buf, sizeof(buf)));
}

TEST_F(SerialConfigTest, EmptyLineIgnored) {
    process("");
}

TEST_F(SerialConfigTest, WhitespaceOnlyIgnored) {
    process("   ");
}

TEST_F(SerialConfigTest, LeadingWhitespaceHandled) {
    process("  AT+SSID=Trimmed");
    char buf[64] = {};
    ASSERT_TRUE(nvs_.getWifiSSID(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "Trimmed");
}

TEST_F(SerialConfigTest, TrailingWhitespaceHandled) {
    process("AT+SSID=Trimmed   ");
    char buf[64] = {};
    ASSERT_TRUE(nvs_.getWifiSSID(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "Trimmed");
}

TEST_F(SerialConfigTest, ATRESETClearsNVS) {
    nvs_.setWifiSSID("ToClear");
    process("AT+RESET");
    NvsSettings fresh;
    fresh.init();
    EXPECT_FALSE(fresh.hasNetworkConfig());
}

TEST_F(SerialConfigTest, SSIDWithSpecialChars) {
    process("AT+SSID=My WiFi 5GHz!");
    char buf[64] = {};
    ASSERT_TRUE(nvs_.getWifiSSID(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "My WiFi 5GHz!");
}

TEST_F(SerialConfigTest, EmptyValue) {
    process("AT+SSID=");
    char buf[64] = {};
    ASSERT_TRUE(nvs_.getWifiSSID(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "");
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
