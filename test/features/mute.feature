Feature: Mute microphone

  Scenario: Mute mic in voice mode shows muted status
    Given the app is open
    When the user clicks the mic button
    Then the status text shows "麦克风已静音"

  Scenario: Unmute mic in voice mode restores listening status
    Given the app is open
    When the user clicks the mic button
    And the user clicks the mic button
    Then the status text shows "我在听，请说..."
