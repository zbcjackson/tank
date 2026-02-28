Feature: WebSocket Reconnection

  Scenario: Automatic reconnection after server restart
    Given the app is open
    When the backend server is stopped
    Then the reconnection overlay appears
    When the backend server is started
    Then the connection is restored
    And the reconnection overlay disappears

  Scenario: Manual reconnect button works
    Given the app is open
    When the backend server is stopped
    Then the reconnection overlay appears
    When I click the "立即重连" button
    Then a reconnection attempt is triggered

  Scenario: Failed state after max retries
    Given the app is open
    When the backend server is stopped permanently
    Then the reconnection overlay shows "正在重新连接..."
    And after 10 failed attempts the overlay shows "连接失败"
    And the "重新连接" button is visible

  Scenario: Conversation history preserved during reconnect
    Given the app is open
    And I have sent a message "hello"
    When the backend server is restarted
    Then the connection is restored
    And my previous message "hello" is still visible
