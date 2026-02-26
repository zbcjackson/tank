Feature: Voice mode

  Scenario: Default mode is voice
    Given the app is open
    Then the voice mode status text is visible

  Scenario: Status text shows listening when connected
    Given the app is open
    Then the status text shows "我在听，请说..."

  Scenario: Voice mode shows thinking status during processing
    Given the app is open
    And the user switches to chat mode
    When the user types "你好" and sends it
    And the user switches to voice mode
    Then the status text shows "TANK 正在思考..."

  Scenario: Voice mode shows speaking status when audio plays
    Given the app is open
    And the user switches to chat mode
    When the user types "你好" and sends it
    And the user switches to voice mode
    Then eventually the status text shows "TANK 正在回复..."
