set(SOURCES
    "main.cpp"
    "app/Assistant.cpp"
    "app/Session.cpp"
    "net/WiFiManager.cpp"
    "net/WsClient.cpp"
    "audio/AudioCapture.cpp"
    "audio/AudioPlayback.cpp"
    "ui/Display.cpp"
    "hal/cores3/Cores3HAL.cpp"
    "hal/pyramid/PyramidHAL.cpp"
    "ui/Cores3Display.cpp"
    "ui/PyramidDisplay.cpp"
)

idf_component_register(
    SRCS ${SOURCES}
    INCLUDE_DIRS "." "app" "audio" "hal" "hal/cores3" "hal/pyramid" "net" "ui"
    REQUIRES
        driver
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_websocket_client
        esp_timer
        esp_lcd
        es7210
)
