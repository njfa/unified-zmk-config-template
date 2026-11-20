#include <zephyr/devicetree.h>
#include <zephyr/drivers/led.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

#include <drivers/behavior.h>
#include <zmk/battery.h>
#include <zmk/ble.h>
#include <zmk/endpoints.h>
#include <zmk/events/battery_state_changed.h>
#include <zmk/events/ble_active_profile_changed.h>

#define PROFILE_STATUS_COMPAT sosho_behavior_profile_status
#define CONNECTION_STATUS_COMPAT sosho_behavior_connection_status

#if DT_HAS_COMPAT_STATUS_OKAY(PROFILE_STATUS_COMPAT) ||                                              \
    DT_HAS_COMPAT_STATUS_OKAY(CONNECTION_STATUS_COMPAT)

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

enum status_color {
    COLOR_RED = BIT(0),
    COLOR_GREEN = BIT(1),
    COLOR_BLUE = BIT(2),
    COLOR_YELLOW = COLOR_RED | COLOR_GREEN,
    COLOR_PURPLE = COLOR_RED | COLOR_BLUE,
    COLOR_CYAN = COLOR_GREEN | COLOR_BLUE,
    COLOR_WHITE = COLOR_RED | COLOR_GREEN | COLOR_BLUE,
};

enum {
    BATTERY_OK_PERCENT = 30,
    BATTERY_LOW_PERCENT = 20,
    BATTERY_CRITICAL_PERCENT = 10,
    BATTERY_BLINK_MS = 2000,
    CONNECTION_BLINK_MS = 1000,
    INDICATOR_GAP_MS = 500,
};

struct status_blink {
    enum status_color color;
    uint16_t duration_ms;
};

static const struct device *const rgb_led = DEVICE_DT_GET(DT_PARENT(DT_ALIAS(led_red)));
static const uint8_t rgb_channels[] = {
    DT_NODE_CHILD_IDX(DT_ALIAS(led_red)),
    DT_NODE_CHILD_IDX(DT_ALIAS(led_green)),
    DT_NODE_CHILD_IDX(DT_ALIAS(led_blue)),
};

// One LED owner; coalesce bursts so outdated states do not queue behind a manual check.
K_SEM_DEFINE(blink_pending, 0, 1);
static atomic_t pending_manual_color;
static atomic_t pending_profile_color;
static atomic_t pending_low_battery;
static atomic_t display_ready;

static enum status_color profile_color(uint8_t profile) {
    if (zmk_ble_profile_is_open(profile)) {
        return COLOR_WHITE;
    }
    return zmk_ble_profile_is_connected(profile) ? COLOR_BLUE : COLOR_PURPLE;
}

static enum status_color connection_color(void) {
    if (zmk_endpoint_get_selected().transport == ZMK_TRANSPORT_USB) {
        return COLOR_CYAN;
    }
    return profile_color(zmk_ble_active_profile_index());
}

static enum status_color battery_color(uint8_t percent) {
    if (percent == 0) {
        return COLOR_PURPLE; // Battery reading not available yet.
    }
    if (percent >= BATTERY_OK_PERCENT) {
        return COLOR_GREEN;
    }
    return percent >= BATTERY_LOW_PERCENT ? COLOR_YELLOW : COLOR_RED;
}

static void show_blink(struct status_blink blink) {
    for (size_t i = 0; i < ARRAY_SIZE(rgb_channels); i++) {
        if (blink.color & BIT(i)) {
            led_on(rgb_led, rgb_channels[i]);
        }
    }
    k_msleep(blink.duration_ms);
    for (size_t i = 0; i < ARRAY_SIZE(rgb_channels); i++) {
        led_off(rgb_led, rgb_channels[i]);
    }
    k_msleep(INDICATOR_GAP_MS);
}

static void queue_manual_blink(enum status_color color) {
    atomic_set(&pending_manual_color, color);
    k_sem_give(&blink_pending);
}

static void status_display_thread(void *unused1, void *unused2, void *unused3) {
    if (!device_is_ready(rgb_led)) {
        LOG_ERR("Right-side status LED is not ready");
        return;
    }

    uint8_t percent = zmk_battery_state_of_charge();
    for (int retry = 0; percent == 0 && retry < 10; retry++) {
        k_msleep(100);
        percent = zmk_battery_state_of_charge();
    }
    show_blink((struct status_blink){battery_color(percent), BATTERY_BLINK_MS});
    atomic_set(&display_ready, 1);
    show_blink((struct status_blink){connection_color(), CONNECTION_BLINK_MS});

    while (true) {
        if (k_sem_take(&blink_pending, K_FOREVER) != 0) {
            continue;
        }
        // Re-signal when work remains; explicit checks take priority over automatic blinks.
        enum status_color color = atomic_set(&pending_manual_color, 0);
        if (color != 0) {
            show_blink((struct status_blink){color, CONNECTION_BLINK_MS});
        } else if (atomic_set(&pending_low_battery, 0)) {
            show_blink((struct status_blink){COLOR_RED, BATTERY_BLINK_MS});
        } else {
            color = atomic_set(&pending_profile_color, 0);
            if (color != 0) {
                show_blink((struct status_blink){color, CONNECTION_BLINK_MS});
            }
        }
        if (atomic_get(&pending_manual_color) || atomic_get(&pending_low_battery) ||
            atomic_get(&pending_profile_color)) {
            k_sem_give(&blink_pending);
        }
    }
}

K_THREAD_DEFINE(status_display, 1024, status_display_thread, NULL, NULL, NULL,
                K_LOWEST_APPLICATION_THREAD_PRIO, 0, 200);

static void show_active_profile(struct k_work *work) {
    atomic_set(&pending_profile_color, profile_color(zmk_ble_active_profile_index()));
    k_sem_give(&blink_pending);
}

K_WORK_DELAYABLE_DEFINE(active_profile_blink, show_active_profile);

static int status_listener(const zmk_event_t *event) {
    if (!atomic_get(&display_ready)) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    const struct zmk_battery_state_changed *battery = as_zmk_battery_state_changed(event);
    if (battery != NULL) {
        if (battery->state_of_charge > 0 && battery->state_of_charge <= BATTERY_CRITICAL_PERCENT) {
            atomic_set(&pending_low_battery, 1);
            k_sem_give(&blink_pending);
        }
    } else {
        // A switch can also trigger a connection event; show only the latest profile state.
        k_work_reschedule(&active_profile_blink, K_MSEC(16));
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(sosho_status, status_listener);
ZMK_SUBSCRIPTION(sosho_status, zmk_battery_state_changed);
ZMK_SUBSCRIPTION(sosho_status, zmk_ble_active_profile_changed);

static int on_release(struct zmk_behavior_binding *binding,
                      struct zmk_behavior_binding_event event) {
    return ZMK_BEHAVIOR_OPAQUE;
}

#if DT_HAS_COMPAT_STATUS_OKAY(PROFILE_STATUS_COMPAT)
static int inspect_profile(struct zmk_behavior_binding *binding,
                           struct zmk_behavior_binding_event event) {
    if (binding->param1 < ZMK_BLE_PROFILE_COUNT) {
        queue_manual_blink(profile_color(binding->param1));
    }
    return ZMK_BEHAVIOR_OPAQUE;
}

#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
static const struct behavior_parameter_value_metadata profile_index_values[] = {{
    .type = BEHAVIOR_PARAMETER_VALUE_TYPE_RANGE,
    .range = {.min = 0, .max = ZMK_BLE_PROFILE_COUNT - 1},
}};
static const struct behavior_parameter_metadata_set profile_params[] = {{
    .param1_values = profile_index_values,
    .param1_values_len = ARRAY_SIZE(profile_index_values),
}};
static const struct behavior_parameter_metadata profile_metadata = {
    .sets = profile_params,
    .sets_len = ARRAY_SIZE(profile_params),
};
#endif

static const struct behavior_driver_api profile_status_api = {
    .locality = BEHAVIOR_LOCALITY_CENTRAL,
    .binding_pressed = inspect_profile,
    .binding_released = on_release,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .parameter_metadata = &profile_metadata,
#endif
};

BEHAVIOR_DT_DEFINE(DT_COMPAT_GET_ANY_STATUS_OKAY(PROFILE_STATUS_COMPAT), NULL, NULL, NULL, NULL,
                   POST_KERNEL, CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &profile_status_api);
#endif

#if DT_HAS_COMPAT_STATUS_OKAY(CONNECTION_STATUS_COMPAT)
static int show_connection(struct zmk_behavior_binding *binding,
                           struct zmk_behavior_binding_event event) {
    queue_manual_blink(connection_color());
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api connection_status_api = {
    .locality = BEHAVIOR_LOCALITY_CENTRAL,
    .binding_pressed = show_connection,
    .binding_released = on_release,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .get_parameter_metadata = zmk_behavior_get_empty_param_metadata,
#endif
};

BEHAVIOR_DT_DEFINE(DT_COMPAT_GET_ANY_STATUS_OKAY(CONNECTION_STATUS_COMPAT), NULL, NULL, NULL, NULL,
                   POST_KERNEL, CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &connection_status_api);
#endif

#endif
