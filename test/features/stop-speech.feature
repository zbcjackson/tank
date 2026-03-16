Feature: Stop speech

  @requires-active-conversation
  Scenario: Stop button appears and works in chat mode
    Given the app is open
    And the user switches to chat mode
    When the user types "写一篇1000字的文章" and sends it
    Then the stop button is visible
    When the user clicks the stop button
    Then the send button is visible

  @requires-active-conversation
  Scenario: Stop button appears in voice mode during response
    Given the app is open
    And the user switches to chat mode
    When the user types "写一篇1000字的文章" and sends it
    And the user switches to voice mode
    Then the voice stop button is visible
