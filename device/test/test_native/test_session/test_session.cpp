// Unit tests for Session state machine.

// Pull in the source files this test needs (no auto-build with build_src_filter=-<*>)
#include "app/Session.cpp"
#include "esp_stubs.cpp"

#include <gtest/gtest.h>

#include "app/Session.h"
#include "esp_stubs.h"

class SessionTest : public ::testing::Test {
protected:
    void SetUp() override {
        esp_stubs_reset();
    }

    Session session;
};

TEST_F(SessionTest, InitialStateIsIdle) {
    EXPECT_EQ(session.getState(), Session::State::IDLE);
}

TEST_F(SessionTest, SetStateTransitions) {
    session.setState(Session::State::CONNECTING);
    EXPECT_EQ(session.getState(), Session::State::CONNECTING);

    session.setState(Session::State::READY);
    EXPECT_EQ(session.getState(), Session::State::READY);

    session.setState(Session::State::LISTENING);
    EXPECT_EQ(session.getState(), Session::State::LISTENING);

    session.setState(Session::State::PROCESSING);
    EXPECT_EQ(session.getState(), Session::State::PROCESSING);

    session.setState(Session::State::SPEAKING);
    EXPECT_EQ(session.getState(), Session::State::SPEAKING);

    session.setState(Session::State::ERROR);
    EXPECT_EQ(session.getState(), Session::State::ERROR);
}

TEST_F(SessionTest, CanTransitionBackToIdle) {
    session.setState(Session::State::ERROR);
    session.setState(Session::State::IDLE);
    EXPECT_EQ(session.getState(), Session::State::IDLE);
}

TEST_F(SessionTest, InitGeneratesSessionIdFromMac) {
    uint8_t mac[6] = {0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC};
    esp_stubs_set_mac(mac);

    session.init();

    EXPECT_STREQ(session.getId(), "device_123456789abc");
    EXPECT_EQ(session.getState(), Session::State::IDLE);
}

TEST_F(SessionTest, InitWithDefaultMac) {
    // Default fake MAC is AA:BB:CC:DD:EE:FF
    session.init();
    EXPECT_STREQ(session.getId(), "device_aabbccddeeff");
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
