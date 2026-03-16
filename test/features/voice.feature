Feature: Voice mode

  Scenario: Default mode is voice
    Given the app is open
    Then the voice mode status text is visible

  Scenario: Voice mode is visible when connected
    Given the app is open
    Then the voice mode status text is visible

  @requires-active-conversation
  Scenario: Voice mode shows thinking status during processing
    Given the app is open
    And the user switches to chat mode
    When the user types "写一篇500字的文章" and sends it
    And the user switches to voice mode
    Then the status text shows "思考中"

  @requires-active-conversation
  Scenario: Voice mode shows speaking status when audio plays
    Given the app is open
    And the user switches to chat mode
    When the user types "写一篇500字的文章" and sends it
    And the user switches to voice mode
    Then eventually the status text shows "回复中"
