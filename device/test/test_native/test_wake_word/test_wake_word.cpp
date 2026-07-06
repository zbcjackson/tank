// Native tests for FrameChunker and SilenceDetector.
// Pure logic, no ESP-IDF — compiled for the host with GoogleTest.

#include <gtest/gtest.h>
#include <cstdint>
#include <vector>

#include "../../../main/audio/FrameChunker.cpp"
#include "../../../main/audio/SilenceDetector.cpp"

// ─── FrameChunker ─────────────────────────────────────────────────────────

TEST(FrameChunker, EmptyBufferPopsNothing) {
    FrameChunker chunker(480);
    int16_t out[480];
    EXPECT_FALSE(chunker.pop(out));
    EXPECT_EQ(chunker.pending(), 0u);
}

TEST(FrameChunker, PartialFrameDoesNotEmit) {
    FrameChunker chunker(480);
    std::vector<int16_t> frame(320, 7);
    chunker.push(frame.data(), frame.size());

    int16_t out[480];
    EXPECT_FALSE(chunker.pop(out));      // 320 < 480, nothing ready
    EXPECT_EQ(chunker.pending(), 320u);
}

TEST(FrameChunker, TwoFramesEmitOneChunkWithRemainder) {
    FrameChunker chunker(480);
    std::vector<int16_t> frame(320, 3);
    chunker.push(frame.data(), frame.size());  // 320
    chunker.push(frame.data(), frame.size());  // 640 total

    int16_t out[480];
    ASSERT_TRUE(chunker.pop(out));        // emits 480
    for (int i = 0; i < 480; i++) EXPECT_EQ(out[i], 3);
    EXPECT_EQ(chunker.pending(), 160u);   // 640 - 480
    EXPECT_FALSE(chunker.pop(out));       // 160 < 480
}

TEST(FrameChunker, ExactMultipleEmitsAllChunks) {
    FrameChunker chunker(320);
    std::vector<int16_t> frame(320, 1);
    chunker.push(frame.data(), frame.size());
    chunker.push(frame.data(), frame.size());
    chunker.push(frame.data(), frame.size());

    int16_t out[320];
    int chunks = 0;
    while (chunker.pop(out)) chunks++;
    EXPECT_EQ(chunks, 3);
    EXPECT_EQ(chunker.pending(), 0u);
}

TEST(FrameChunker, PreservesSampleOrderAcrossChunkBoundary) {
    FrameChunker chunker(4);
    int16_t a[6] = {1, 2, 3, 4, 5, 6};
    chunker.push(a, 6);

    int16_t out[4];
    ASSERT_TRUE(chunker.pop(out));
    EXPECT_EQ(out[0], 1); EXPECT_EQ(out[3], 4);

    int16_t b[2] = {7, 8};
    chunker.push(b, 2);                   // buffer now 5,6,7,8
    ASSERT_TRUE(chunker.pop(out));
    EXPECT_EQ(out[0], 5); EXPECT_EQ(out[1], 6);
    EXPECT_EQ(out[2], 7); EXPECT_EQ(out[3], 8);
}

TEST(FrameChunker, ResetDropsPending) {
    FrameChunker chunker(480);
    std::vector<int16_t> frame(320, 9);
    chunker.push(frame.data(), frame.size());
    chunker.reset();
    EXPECT_EQ(chunker.pending(), 0u);
}

// ─── SilenceDetector ──────────────────────────────────────────────────────

static SilenceDetector::Config makeCfg() {
    // speech RMS 500, 3 quiet frames to end, need 2 speech frames, cap at 100.
    return SilenceDetector::Config{500, 3, 2, 100};
}

static std::vector<int16_t> loud(size_t n = 320) {
    return std::vector<int16_t>(n, 4000);   // RMS ~4000 > 500
}

static std::vector<int16_t> quiet(size_t n = 320) {
    return std::vector<int16_t>(n, 0);      // RMS 0 < 500
}

TEST(SilenceDetector, EndsAfterSilenceFollowingSpeech) {
    SilenceDetector det(makeCfg());
    auto sp = loud();
    auto si = quiet();

    EXPECT_FALSE(det.update(sp.data(), sp.size()));  // speech 1
    EXPECT_FALSE(det.update(sp.data(), sp.size()));  // speech 2 (floor met)
    EXPECT_FALSE(det.update(si.data(), si.size()));  // silence 1
    EXPECT_FALSE(det.update(si.data(), si.size()));  // silence 2
    EXPECT_TRUE(det.update(si.data(), si.size()));   // silence 3 -> end
    EXPECT_FALSE(det.endedByCap());
}

TEST(SilenceDetector, LeadingSilenceDoesNotEndBeforeSpeech) {
    SilenceDetector det(makeCfg());
    auto si = quiet();
    // Many silent frames before any speech: min_speech floor blocks the end.
    for (int i = 0; i < 10; i++) {
        EXPECT_FALSE(det.update(si.data(), si.size()));
    }
}

TEST(SilenceDetector, InterruptedSilenceResetsTrailingCount) {
    SilenceDetector det(makeCfg());
    auto sp = loud();
    auto si = quiet();

    det.update(sp.data(), sp.size());
    det.update(sp.data(), sp.size());
    det.update(si.data(), si.size());   // silence 1
    det.update(si.data(), si.size());   // silence 2
    det.update(sp.data(), sp.size());   // speech resets trailing silence
    EXPECT_FALSE(det.update(si.data(), si.size()));  // silence 1 again
    EXPECT_FALSE(det.update(si.data(), si.size()));  // silence 2
    EXPECT_TRUE(det.update(si.data(), si.size()));   // silence 3 -> end
}

TEST(SilenceDetector, MaxCapForcesEndInNoisyRoom) {
    SilenceDetector det(makeCfg());
    auto sp = loud();
    bool ended = false;
    for (int i = 0; i < 100; i++) {
        if (det.update(sp.data(), sp.size())) { ended = true; break; }
    }
    ASSERT_TRUE(ended);
    EXPECT_TRUE(det.endedByCap());
}

TEST(SilenceDetector, ResetClearsState) {
    SilenceDetector det(makeCfg());
    auto sp = loud();
    auto si = quiet();
    det.update(sp.data(), sp.size());
    det.update(sp.data(), sp.size());
    det.reset();
    // After reset, trailing silence alone (no fresh speech) must not end.
    for (int i = 0; i < 5; i++) {
        EXPECT_FALSE(det.update(si.data(), si.size()));
    }
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
