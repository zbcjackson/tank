Feature: Conversations

  Background:
    Given the app is open
    And the user switches to chat mode

  Scenario: Conversation list opens and closes
    When the user clicks the conversations button
    Then the conversation list sidebar is visible
    When the user closes the conversation list
    Then the conversation list sidebar is hidden

  @requires-active-conversation
  Scenario: New conversation clears chat
    When the user types "hello" and sends it
    And eventually an assistant message appears
    And the user clicks the conversations button
    And the user clicks new conversation
    Then the conversation is empty

  @requires-active-conversation
  Scenario: Conversation appears in list after chatting
    When the user types "hello" and sends it
    And eventually an assistant message appears
    And the user clicks the conversations button
    Then the conversation list contains at least 1 conversation
