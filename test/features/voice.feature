Feature: Voice mode

  Scenario: Default mode is voice
    Given the app is open
    Then the voice mode status text is visible

  Scenario: Status text shows listening when connected
    Given the app is open
    Then the status text shows "我在听，请说..."
