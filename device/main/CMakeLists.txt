set(SOURCES
    "main.cpp"
    "app/Assistant.cpp"
    "app/Session.cpp"
    "net/WiFiManager.cpp"
    "net/WsClient.cpp"
    "audio/AudioCapture.cpp"
    "audio/AudioPlayback.cpp"
    "ui/Display.cpp"
    "ui/Cores3Display.cpp"
    "ui/PyramidDisplay.cpp"
    "settings/NvsSettings.cpp"
    "settings/SerialConfig.cpp"
    "hal/cores3/Cores3HAL.cpp"
    "hal/pyramid/PyramidHAL.cpp"
)

# LVGL screen files only for CoreS3 (Pyramid has no LCD widget UI)
if(CONFIG_IDF_TARGET_ESP32S3)
    # Both targets are S3, so gate on our own define
endif()
list(APPEND SOURCES
    "ui/screens/MainScreen.cpp"
    "ui/screens/SettingsScreen.cpp"
)

idf_component_register(
    SRCS ${SOURCES}
    INCLUDE_DIRS "." "app" "audio" "hal" "hal/cores3" "hal/pyramid" "net" "ui" "ui/screens" "settings"
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
        esp_lvgl_port
)
