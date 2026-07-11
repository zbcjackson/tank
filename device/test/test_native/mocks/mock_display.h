#pragma once

// GMock implementation of the Display interface.
// Use in tests that verify Assistant → Display interactions.

#include <gmock/gmock.h>
#include "ui/Display.h"

class MockDisplay : public Display {
public:
    MOCK_METHOD(bool, init, (), (override));
    MOCK_METHOD(void, showStatus, (const char* status), (override));
    MOCK_METHOD(void, showUserText, (const char* text), (override));
    MOCK_METHOD(void, showAssistantText, (const char* text), (override));
    MOCK_METHOD(void, showThinking, (bool active), (override));
    MOCK_METHOD(void, showError, (const char* error), (override));
    MOCK_METHOD(void, clear, (), (override));
    MOCK_METHOD(bool, pollPressed, (), (override));
    MOCK_METHOD(void, showTalkState, (bool listening), (override));
    MOCK_METHOD(bool, consumeNewConversationRequest, (), (override));
    MOCK_METHOD(bool, consumeCallModeRequest, (), (override));
    MOCK_METHOD(bool, consumeHangupRequest, (), (override));
};
