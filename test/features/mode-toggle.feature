Feature: Mode toggle

  Scenario: Toggle voice to chat shows chat input
    Given the app is open
    When the user switches to chat mode
    Then the chat input is visible

  Scenario: Toggle chat back to voice shows status text
    Given the app is open
    When the user switches to chat mode
    And the user switches to voice mode
    Then the voice mode status text is visible
