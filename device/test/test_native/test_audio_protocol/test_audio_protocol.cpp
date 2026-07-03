// Unit tests for audio frame header parsing.

#include "net/WsProtocol.cpp"

#include <gtest/gtest.h>
#include "net/WsProtocol.h"

TEST(AudioProtocol, ValidFrame16kHzMono) {
    uint8_t frame[12] = {};
    // Magic: 0x544B little-endian
    frame[0] = 0x4B; frame[1] = 0x54;
    // Sample rate: 16000 (0x3E80) little-endian
    frame[2] = 0x80; frame[3] = 0x3E; frame[4] = 0x00; frame[5] = 0x00;
    // Channels: 1
    frame[6] = 0x01; frame[7] = 0x00;
    // PCM data (2 samples)
    frame[8] = 0x00; frame[9] = 0x10;
    frame[10] = 0xFF; frame[11] = 0x7F;

    AudioFrameHeader hdr = {};
    ASSERT_TRUE(parseAudioFrameHeader(frame, 12, &hdr));
    EXPECT_EQ(hdr.magic, 0x544B);
    EXPECT_EQ(hdr.sample_rate, 16000u);
    EXPECT_EQ(hdr.channels, 1);
}

TEST(AudioProtocol, ValidFrame24kHzStereo) {
    uint8_t frame[8] = {};
    frame[0] = 0x4B; frame[1] = 0x54;  // magic
    // 24000 = 0x5DC0
    frame[2] = 0xC0; frame[3] = 0x5D; frame[4] = 0x00; frame[5] = 0x00;
    frame[6] = 0x02; frame[7] = 0x00;  // 2 channels

    AudioFrameHeader hdr = {};
    ASSERT_TRUE(parseAudioFrameHeader(frame, 8, &hdr));
    EXPECT_EQ(hdr.sample_rate, 24000u);
    EXPECT_EQ(hdr.channels, 2);
}

TEST(AudioProtocol, RejectsWrongMagic) {
    uint8_t frame[8] = {0x00, 0x00, 0x80, 0x3E, 0x00, 0x00, 0x01, 0x00};
    AudioFrameHeader hdr = {};
    EXPECT_FALSE(parseAudioFrameHeader(frame, 8, &hdr));
}

TEST(AudioProtocol, RejectsShortFrame) {
    uint8_t frame[4] = {0x4B, 0x54, 0x80, 0x3E};
    AudioFrameHeader hdr = {};
    EXPECT_FALSE(parseAudioFrameHeader(frame, 4, &hdr));
}

TEST(AudioProtocol, RejectsEmptyData) {
    AudioFrameHeader hdr = {};
    EXPECT_FALSE(parseAudioFrameHeader(nullptr, 0, &hdr));
}

TEST(AudioProtocol, ExactHeaderSizeIsValid) {
    uint8_t frame[8] = {};
    frame[0] = 0x4B; frame[1] = 0x54;
    frame[2] = 0x80; frame[3] = 0x3E; frame[4] = 0x00; frame[5] = 0x00;
    frame[6] = 0x01; frame[7] = 0x00;

    AudioFrameHeader hdr = {};
    ASSERT_TRUE(parseAudioFrameHeader(frame, 8, &hdr));
    EXPECT_EQ(hdr.sample_rate, 16000u);
}

TEST(AudioProtocol, LargePayloadStillParsesHeader) {
    // 8-byte header + 640 bytes of PCM (320 samples)
    std::vector<uint8_t> frame(648, 0);
    frame[0] = 0x4B; frame[1] = 0x54;
    frame[2] = 0x80; frame[3] = 0x3E; frame[4] = 0x00; frame[5] = 0x00;
    frame[6] = 0x01; frame[7] = 0x00;

    AudioFrameHeader hdr = {};
    ASSERT_TRUE(parseAudioFrameHeader(frame.data(), frame.size(), &hdr));
    EXPECT_EQ(hdr.sample_rate, 16000u);
    EXPECT_EQ(hdr.channels, 1);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
