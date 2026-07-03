// Smoke test verifying GMock headers compile and mocks are usable.
// This validates mock_display.h and mock_board_hal.h for future Assistant tests.

#include <gtest/gtest.h>
#include <gmock/gmock.h>

#include "mock_display.h"
#include "mock_board_hal.h"

using ::testing::Return;
using ::testing::_;

TEST(MockSmoke, DisplayMockRecordsCalls) {
    MockDisplay display;
    EXPECT_CALL(display, showStatus(_)).Times(1);
    EXPECT_CALL(display, init()).WillOnce(Return(true));

    EXPECT_TRUE(display.init());
    display.showStatus("Connecting...");
}

TEST(MockSmoke, BoardHALMockRecordsCalls) {
    MockBoardHAL hal;
    EXPECT_CALL(hal, setVolume(70)).Times(1);
    EXPECT_CALL(hal, getMicI2SPort()).WillOnce(Return(1));

    hal.setVolume(70);
    EXPECT_EQ(hal.getMicI2SPort(), 1);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
