Feature: WebSocket connection

  Scenario: App connects to backend and shows ready state
    Given the app is open
    Then the status text shows "我在听，请说..."
