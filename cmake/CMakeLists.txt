zephyr_library()
zephyr_library_sources_ifdef(CONFIG_ZMK_POINTING ../src/behavior_encoder_mouse_scroll.c)
zephyr_library_sources_ifdef(CONFIG_ZMK_SPLIT_ROLE_CENTRAL ../src/behavior_connection_status.c)
