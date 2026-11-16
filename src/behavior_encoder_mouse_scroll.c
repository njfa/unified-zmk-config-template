/*
 * Copyright (c) 2026 Your Name
 * SPDX-License-Identifier: MIT
 *
 * Based on elekit-official/zmk_encoder at
 * 1a34a5561f08eb7130823760fe597458f477e6db.
 * Keep encoder trigger timing unchanged; scale only the outgoing scroll report.
 * See behavior_encoder_mouse_scroll.LICENSE for the upstream MIT license.
 */

#define DT_DRV_COMPAT sosho_behavior_encoder_mouse_scroll

#include <errno.h>
#include <stdlib.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>
#include <drivers/behavior.h>
#include <zmk/behavior.h>
#include <zmk/keymap.h>
#include <zmk/virtual_key_position.h>

#if !defined(CONFIG_ZMK_SPLIT) || defined(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
#include <zmk/hid.h>
#include <zmk/endpoints.h>
#include <dt-bindings/zmk/pointing.h>
#endif

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

struct encoder_scroll_config {
    int multiplier;
};

struct encoder_scroll_data {
    struct sensor_value remainder[ZMK_KEYMAP_SENSORS_LEN][ZMK_KEYMAP_LAYERS_LEN];
    int32_t triggers[ZMK_KEYMAP_SENSORS_LEN][ZMK_KEYMAP_LAYERS_LEN];
};

static int encoder_scroll_accept_data(
    struct zmk_behavior_binding *binding, struct zmk_behavior_binding_event event,
    const struct zmk_sensor_config *sensor_config, size_t channel_data_size,
    const struct zmk_sensor_channel_data *channel_data) {
    if (channel_data_size == 0 || channel_data == NULL) {
        return -EINVAL;
    }

    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    if (dev == NULL) {
        return -ENODEV;
    }

    struct encoder_scroll_data *data = dev->data;
    const struct sensor_value value = channel_data[0].value;
    int sensor_index = ZMK_SENSOR_POSITION_FROM_VIRTUAL_KEY_POSITION(event.position);
    struct sensor_value *rem = &data->remainder[sensor_index][event.layer];

    if ((value.val1 > 0 && rem->val1 < 0) || (value.val1 < 0 && rem->val1 > 0)) {
        rem->val1 = 0;
        rem->val2 = 0;
    }

    rem->val1 += value.val1;
    rem->val2 += value.val2;
    if (abs(rem->val2) >= 1000000) {
        rem->val1 += rem->val2 / 1000000;
        rem->val2 %= 1000000;
    }

    int trigger_degrees = 360 / sensor_config->triggers_per_rotation;
    data->triggers[sensor_index][event.layer] = rem->val1 / trigger_degrees;
    rem->val1 %= trigger_degrees;
    return 0;
}

static int encoder_scroll_process(struct zmk_behavior_binding *binding,
                                  struct zmk_behavior_binding_event event,
                                  enum behavior_sensor_binding_process_mode mode) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    if (dev == NULL) {
        return -ENODEV;
    }

    struct encoder_scroll_data *data = dev->data;
    int sensor_index = ZMK_SENSOR_POSITION_FROM_VIRTUAL_KEY_POSITION(event.position);
    int32_t triggers = data->triggers[sensor_index][event.layer];
    data->triggers[sensor_index][event.layer] = 0;

    if (mode != BEHAVIOR_SENSOR_BINDING_PROCESS_MODE_TRIGGER || triggers == 0) {
        return ZMK_BEHAVIOR_TRANSPARENT;
    }

#if !defined(CONFIG_ZMK_SPLIT) || defined(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    const struct encoder_scroll_config *config = dev->config;
    uint32_t param = triggers > 0 ? binding->param1 : binding->param2;
    int16_t horizontal = MOVE_X_DECODE(param);
    int16_t vertical = MOVE_Y_DECODE(param);
    int amount = abs(triggers) * config->multiplier;

    horizontal = (horizontal > 0) - (horizontal < 0);
    vertical = (vertical > 0) - (vertical < 0);

    // Split large movements into reports to avoid overflowing HID wheel fields.
    while (amount > 0) {
        int step = MIN(amount, 127);
        zmk_hid_mouse_scroll_set(horizontal * step, vertical * step);
        zmk_endpoint_send_mouse_report();
        amount -= step;
    }

    zmk_hid_mouse_scroll_set(0, 0);
    zmk_endpoint_send_mouse_report();
    return ZMK_BEHAVIOR_OPAQUE;
#else
    return ZMK_BEHAVIOR_TRANSPARENT;
#endif
}

static const struct behavior_driver_api encoder_scroll_driver_api = {
    .sensor_binding_accept_data = encoder_scroll_accept_data,
    .sensor_binding_process = encoder_scroll_process,
};

#define ENCODER_SCROLL_INST(n)                                                                     \
    BUILD_ASSERT(DT_INST_PROP(n, scroll_multiplier) > 0, "Scroll multiplier must be positive");     \
    static const struct encoder_scroll_config encoder_scroll_config_##n = {                       \
        .multiplier = DT_INST_PROP(n, scroll_multiplier),                                         \
    };                                                                                            \
    static struct encoder_scroll_data encoder_scroll_data_##n;                                    \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, &encoder_scroll_data_##n,                               \
                            &encoder_scroll_config_##n, POST_KERNEL,                              \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &encoder_scroll_driver_api);

DT_INST_FOREACH_STATUS_OKAY(ENCODER_SCROLL_INST)
