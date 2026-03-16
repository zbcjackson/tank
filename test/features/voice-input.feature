@fake-audio
Feature: Voice input via fake audio

  Scenario: User speech is transcribed and shown in chat
    Given the app is open
    And the user switches to chat mode
    When the WAV fixture "你好.wav" is sent over the WebSocket
    Then eventually a user transcript appears in the conversation
