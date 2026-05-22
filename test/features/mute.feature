Feature: Mute microphone

  Scenario: Mic toggle switches between on and off in continuous mode
    Given the app is open
    And the listen mode is "continuous"
    Then the mic button shows muted state
    When the user clicks the mic button
    Then the mic button shows unmuted state
    When the user clicks the mic button
    Then the mic button shows muted state
