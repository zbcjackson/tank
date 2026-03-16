Feature: Mute microphone

  Scenario: Mute mic toggles mic state
    Given the app is open
    When the user clicks the mic button
    Then the mic button shows muted state
    When the user clicks the mic button
    Then the mic button shows unmuted state
