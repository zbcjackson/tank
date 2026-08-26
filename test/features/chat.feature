Feature: Chat mode

  Background:
    Given the app is open
    And the user switches to chat mode

  Scenario: Empty state shows placeholder
    When the user clicks the conversations button
    And the user clicks new conversation
    Then the empty state text "开始对话吧" is visible

  Scenario: User message appears in conversation
    When the user types "你好" and sends it
    Then the user message "你好" is visible in the conversation

  @requires-active-conversation
  Scenario: Sending a message triggers assistant response
    When the user types "现在几点" and sends it
    Then the typing indicator is visible
    And eventually an assistant message appears
    And the typing indicator disappears

  @requires-active-conversation
  Scenario: Stop button replaces send button during processing
    When the user types "你好" and sends it
    Then the stop button is visible
    And eventually the send button is visible

  # P0-5: sentence-level TTS streaming — first audio must land while the
  # LLM text is still streaming (not after the whole turn finishes).
  @requires-active-conversation @streaming-audio
  Scenario: Long answer audio starts before text finishes streaming
    When the user sends a long-answer prompt with audio streaming tracked
    Then the first audio frame arrives before the response text completes
