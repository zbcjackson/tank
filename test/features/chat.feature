Feature: Chat mode

  Background:
    Given the app is open
    And the user switches to chat mode

  Scenario: Empty state shows placeholder
    Then the empty state text "开始对话吧" is visible

  Scenario: Sending a message triggers assistant response
    When the user types "现在几点" and sends it
    Then the typing indicator is visible
    And eventually an assistant message appears
    And the typing indicator disappears

  Scenario: Send button disabled during processing
    When the user types "你好" and sends it
    Then the send button is disabled
    And eventually the send button is enabled
