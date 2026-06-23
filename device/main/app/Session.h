#pragma once

#include <cstdint>

/// Session ID management and connection state.
class Session {
public:
    enum class State {
        IDLE,
        CONNECTING,
        READY,
        LISTENING,
        PROCESSING,
        SPEAKING,
        ERROR,
    };

    /// Get the session ID (persisted in NVS or generated).
    const char* getId() const { return session_id_; }

    /// Get current state.
    State getState() const { return state_; }

    /// Set state.
    void setState(State s) { state_ = s; }

    /// Generate or load session ID.
    void init();

private:
    char session_id_[64] = {};
    State state_ = State::IDLE;
};
