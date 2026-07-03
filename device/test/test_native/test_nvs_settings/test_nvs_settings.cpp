// Unit tests for NvsSettings (backed by in-memory NVS fake).

#include "settings/NvsSettings.cpp"
#include "nvs_stubs.cpp"
#include "esp_stubs.cpp"

#include <gtest/gtest.h>
#include "settings/NvsSettings.h"
#include "nvs_stubs.h"

class NvsSettingsTest : public ::testing::Test {
protected:
    void SetUp() override {
        nvs_stub_reset();
        settings_.init();
    }

    NvsSettings settings_;
};

TEST_F(NvsSettingsTest, InitSucceeds) {
    NvsSettings fresh;
    nvs_stub_reset();
    EXPECT_TRUE(fresh.init());
}

TEST_F(NvsSettingsTest, DefaultVolume) {
    EXPECT_EQ(settings_.getVolume(), 70);
}

TEST_F(NvsSettingsTest, SetAndGetVolume) {
    settings_.setVolume(42);
    EXPECT_EQ(settings_.getVolume(), 42);
}

TEST_F(NvsSettingsTest, VolumeZero) {
    settings_.setVolume(0);
    EXPECT_EQ(settings_.getVolume(), 0);
}

TEST_F(NvsSettingsTest, VolumeMax) {
    settings_.setVolume(100);
    EXPECT_EQ(settings_.getVolume(), 100);
}

TEST_F(NvsSettingsTest, DefaultBackendPort) {
    EXPECT_EQ(settings_.getBackendPort(), CONFIG_BACKEND_PORT);
}

TEST_F(NvsSettingsTest, SetAndGetBackendPort) {
    settings_.setBackendPort(9000);
    EXPECT_EQ(settings_.getBackendPort(), 9000);
}

TEST_F(NvsSettingsTest, WifiSSIDNotStoredReturnsFalse) {
    char buf[64];
    EXPECT_FALSE(settings_.getWifiSSID(buf, sizeof(buf)));
}

TEST_F(NvsSettingsTest, SetAndGetWifiSSID) {
    settings_.setWifiSSID("MyNetwork");
    char buf[64] = {};
    ASSERT_TRUE(settings_.getWifiSSID(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "MyNetwork");
}

TEST_F(NvsSettingsTest, WifiPasswordNotStoredReturnsFalse) {
    char buf[64];
    EXPECT_FALSE(settings_.getWifiPassword(buf, sizeof(buf)));
}

TEST_F(NvsSettingsTest, SetAndGetWifiPassword) {
    settings_.setWifiPassword("secret123");
    char buf[64] = {};
    ASSERT_TRUE(settings_.getWifiPassword(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "secret123");
}

TEST_F(NvsSettingsTest, BackendHostNotStoredReturnsFalse) {
    char buf[64];
    EXPECT_FALSE(settings_.getBackendHost(buf, sizeof(buf)));
}

TEST_F(NvsSettingsTest, SetAndGetBackendHost) {
    settings_.setBackendHost("192.168.1.50");
    char buf[64] = {};
    ASSERT_TRUE(settings_.getBackendHost(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "192.168.1.50");
}

TEST_F(NvsSettingsTest, HasNetworkConfigFalseWhenEmpty) {
    EXPECT_FALSE(settings_.hasNetworkConfig());
}

TEST_F(NvsSettingsTest, HasNetworkConfigTrueWhenSSIDSet) {
    settings_.setWifiSSID("TestNet");
    EXPECT_TRUE(settings_.hasNetworkConfig());
}

TEST_F(NvsSettingsTest, FactoryResetClearsAll) {
    settings_.setVolume(99);
    settings_.setWifiSSID("ToBeCleared");
    settings_.setBackendHost("10.0.0.1");

    settings_.factoryReset();  // clears NVS, calls esp_restart (no-op in tests)

    // After reset, re-init to simulate reboot
    NvsSettings fresh;
    fresh.init();
    EXPECT_EQ(fresh.getVolume(), 70);  // back to default
    EXPECT_FALSE(fresh.hasNetworkConfig());
}

TEST_F(NvsSettingsTest, OverwriteExistingValue) {
    settings_.setWifiSSID("First");
    settings_.setWifiSSID("Second");
    char buf[64] = {};
    ASSERT_TRUE(settings_.getWifiSSID(buf, sizeof(buf)));
    EXPECT_STREQ(buf, "Second");
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
