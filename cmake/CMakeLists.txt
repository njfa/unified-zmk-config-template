zephyr_library()
zephyr_library_sources_ifdef(CONFIG_ZMK_POINTING ../src/behavior_encoder_mouse_scroll.c)
