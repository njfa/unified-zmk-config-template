"""Static layout checks; these do not replace a ZMK build or hardware tests."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "config/sosho.keymap").read_text()
LAYERS = {
    name: re.findall(r"&\w+(?:\s+[^&]+)?", bindings.strip())
    for name, bindings in re.findall(
        r"(\w+)\s*\{\s*bindings\s*=\s*<(.*?)>;",
        SOURCE.split("keymap {", 1)[1], re.S
    )
}
LAYERS = {
    name: [" ".join(binding.split()) for binding in bindings]
    for name, bindings in LAYERS.items()
}


class KeymapTests(unittest.TestCase):
    def test_layer_order_and_binding_counts(self):
        self.assertEqual(
            list(LAYERS),
            ["default_layer", "layer_1", "layer_2", "number_over_nav",
             "layer_4", "layer_5", "connection_layer", "boot_arm_layer",
             "maintenance_layer"],
        )
        for name, bindings in LAYERS.items():
            with self.subTest(layer=name):
                self.assertEqual(len(bindings), 44)
                for binding in bindings:
                    behavior, *args = binding.split()
                    self.assertEqual(
                        len(args),
                        {"&kp": 1, "&mt": 2, "&lt": 2, "&mo": 1,
                         "&trans": 0, "&mkp": 1, "&bt": None, "&out": 1,
                          "&bspc_del": 0, "&profile_key": 2, "&boot_hold": 2,
                           "&conn_status": 0, "&none": 0}[behavior]
                        if behavior != "&bt"
                        else (2 if args[0] == "BT_SEL" else 1),
                    )

    def test_base_layout(self):
        expected = [
            "&kp F11", *[f"&kp {k}" for k in "QWERTYUIOP"], "&kp F12",
            "&kp LANG1", *[f"&kp {k}" for k in "ASDFGHJKL"],
            "&mt LCTRL TAB", "&lt FN LANG2",
            "&kp LGUI", "&mt LSHFT Z", *[f"&kp {k}" for k in "XCVBNM"],
            "&kp COMMA", "&kp DOT", "&kp SLASH", "&kp LALT",
            "&kp LALT", "&kp JP_ZKHK", "&lt NUM SPACE", "&lt ALT ESC",
            "&bspc_del", "&lt NAV ENTER", "&kp LC(LA(DEL))", "&mo CONNECT",
        ]
        self.assertEqual(LAYERS["default_layer"], expected)

    def test_jis_hid_positions(self):
        for alias, code in {
            "JP_AT": "LBKT", "JP_COLON": "SQT", "JP_CARET": "EQUAL",
            "JP_LBKT": "RBKT", "JP_RBKT": "NUHS",
            "JP_YEN": "INT_YEN", "JP_BSLH": "INT_RO", "JP_ZKHK": "GRAVE",
        }.items():
            self.assertRegex(SOURCE, rf"#define {alias} {code}\b")

    def test_layer_access(self):
        for name, number in {"NUM": 1, "NAV": 2, "NUM_OVER_NAV": 3,
                             "FN": 4, "ALT": 5, "CONNECT": 6,
                             "BOOT_ARM": 7, "MAINTENANCE": 8}.items():
            self.assertRegex(SOURCE, rf"#define {name} {number}\b")
        self.assertEqual(LAYERS["layer_1"][40], "&kp DEL")
        self.assertEqual(
            LAYERS["layer_2"][18:22],
            ["&kp LEFT", "&kp DOWN", "&kp UP", "&kp RIGHT"],
        )
        self.assertEqual(
            LAYERS["layer_4"][1:11], [f"&kp F{n}" for n in range(1, 11)]
        )
        self.assertEqual(LAYERS["layer_5"][41], "&kp LA(ENTER)")
        self.assertNotIn("NUM_ALT", SOURCE)

    def test_alt_layer_top_letters(self):
        self.assertEqual(
            LAYERS["layer_5"][1:11],
            [f"&kp LA({key})" for key in "QWERTYUIOP"],
        )

    def test_no_removed_mod_taps(self):
        self.assertNotRegex(SOURCE, r"&mt\s+\w+\s+(?:SLASH|LANG1|LANG2)\b")

    def test_z_hold_is_left_shift(self):
        self.assertEqual(LAYERS["default_layer"][25], "&mt LSHFT Z")
        for layer, tap_key in (
            ("layer_1", "N6"), ("layer_2", "SEMI"), ("number_over_nav", "N6"),
        ):
            with self.subTest(layer=layer):
                self.assertEqual(LAYERS[layer][25], f"&mt LSHFT {tap_key}")
        for layer in ("layer_4", "connection_layer"):
            self.assertEqual(LAYERS[layer][25], "&trans")

    def test_tapping_term(self):
        for behavior in ("mt", "lt"):
            self.assertRegex(
                SOURCE,
                rf'&{behavior}\s*\{{\s*flavor = "tap-preferred";'
                r"\s*tapping-term-ms = <180>;",
            )

    def test_one_shot_modifiers_release_on_next_key_press(self):
        block = re.search(r"&sk\s*\{(.*?)\};", SOURCE, re.S)[1]
        self.assertIn("quick-release;", block)

    def test_quick_tap_does_not_force_repeat(self):
        for behavior in ("mt", "lt"):
            block = re.search(rf"&{behavior}\s*\{{(.*?)\}};", SOURCE, re.S)[1]
            self.assertIn("quick-tap-ms = <0>;", block)

    def test_mouse_combos_use_the_requested_layers(self):
        combos = dict(re.findall(r"(combo_\w+)\s*\{(.*?)\};", SOURCE, re.S))
        combos = {name: block for name, block in combos.items() if "&mkp " in block}
        expected = {
            "combo_LCLK": ("19 20", "LCLK", 50, "BASE"),
            "combo_RCLK": ("20 21", "RCLK", 50, "BASE"),
            "combo_MCLK": ("19 21", "MCLK", 90, "BASE"),
            "combo_BACK": ("19 20", "MB4", 50, "NUM NUM_OVER_NAV"),
            "combo_FORWARD": ("20 21", "MB5", 50, "NUM NUM_OVER_NAV"),
        }
        self.assertEqual(set(combos), set(expected))
        self.assertRegex(SOURCE, r"#define NUM 1\b")
        self.assertEqual(LAYERS["default_layer"][38], "&lt NUM SPACE")
        for name, (positions, button, timeout, layer) in expected.items():
            with self.subTest(combo=name):
                block = combos[name]
                self.assertIn(f"key-positions = <{positions}>;", block)
                self.assertIn(f"bindings = <&mkp {button}>;", block)
                self.assertIn(f"layers = <{layer}>;", block)
                self.assertIn(f"timeout-ms = <{timeout}>;", block)
        for position, key in ((14, "S"), (15, "D"), (16, "F"),
                              (19, "J"), (20, "K"), (21, "L")):
            self.assertEqual(LAYERS["default_layer"][position], f"&kp {key}")

    def test_fj_is_one_shot_ctrl_after_typing_idle(self):
        combos = dict(re.findall(r"(combo_\w+)\s*\{(.*?)\};", SOURCE, re.S))
        self.assertEqual(len(combos), 7)
        self.assertNotIn("combo_LANG1", combos)
        self.assertNotIn("combo_LANG2", combos)
        self.assertNotIn("combo_ZKHK", combos)
        block = combos["combo_CTRL"]
        self.assertIn("timeout-ms = <30>;", block)
        self.assertIn("require-prior-idle-ms = <150>;", block)
        self.assertIn("key-positions = <16 19>;", block)
        self.assertIn("bindings = <&sk LCTRL>;", block)
        self.assertIn("layers = <BASE>;", block)
        for position, key in ((16, "F"), (19, "J")):
            self.assertEqual(LAYERS["default_layer"][position], f"&kp {key}")
        self.assertEqual(LAYERS["default_layer"][12], "&kp LANG1")
        self.assertEqual(LAYERS["default_layer"][23], "&lt FN LANG2")
        self.assertEqual(LAYERS["default_layer"][22], "&mt LCTRL TAB")
        self.assertEqual(LAYERS["default_layer"][37], "&kp JP_ZKHK")

    def test_dk_is_one_shot_shift_on_base_num_and_nav(self):
        block = re.search(r"combo_SHIFT\s*\{(.*?)\};", SOURCE, re.S)[1]
        self.assertIn("key-positions = <15 20>;", block)
        self.assertIn("bindings = <&sk LSHFT>;", block)
        self.assertIn("layers = <BASE NUM NAV NUM_OVER_NAV>;", block)
        self.assertIn("timeout-ms = <50>;", block)
        self.assertEqual(LAYERS["default_layer"][15], "&kp D")
        self.assertEqual(LAYERS["default_layer"][20], "&kp K")

    def test_shift_backspace_is_unshifted_delete(self):
        block = re.search(
            r"bspc_del:\s*backspace_delete\s*\{(.*?)\};", SOURCE, re.S
        )[1]
        self.assertIn('compatible = "zmk,behavior-mod-morph";', block)
        self.assertIn("#binding-cells = <0>;", block)
        self.assertIn("bindings = <&kp BSPC>, <&kp DEL>;", block)
        self.assertIn("mods = <(MOD_LSFT | MOD_RSFT)>;", block)
        self.assertIn("keep-mods = <0>;", block)
        self.assertEqual(LAYERS["default_layer"][40], "&bspc_del")
        # The number layer keeps its existing, unconditional Delete binding.
        self.assertEqual(LAYERS["layer_1"][40], "&kp DEL")
        for layer in ("layer_2", "layer_4", "layer_5", "connection_layer"):
            self.assertEqual(LAYERS[layer][40], "&trans")

    def test_revised_outer_keys(self):
        base = LAYERS["default_layer"]
        self.assertEqual(base[12], "&kp LANG1")
        self.assertEqual(base[23], "&lt FN LANG2")
        self.assertEqual(base[24], "&kp LGUI")
        self.assertEqual(base[35], "&kp LALT")
        for layer in ("layer_1", "layer_2", "layer_4", "layer_5",
                      "connection_layer"):
            for position in (12, 23, 24, 35):
                expected = (
                    "&bt BT_CLR"
                    if layer == "connection_layer" and position == 35
                    else "&trans"
                )
                self.assertEqual(LAYERS[layer][position], expected)

    def test_function_layer_has_only_function_keys_and_transparency(self):
        self.assertEqual(
            LAYERS["layer_4"][:12],
            ["&kp F11", *[f"&kp F{n}" for n in range(1, 11)], "&kp F12"],
        )
        self.assertEqual(LAYERS["layer_4"][12:], ["&trans"] * 32)

    def test_space_on_nav_uses_a_higher_momentary_number_layer(self):
        self.assertEqual(LAYERS["layer_2"][38], "&lt NUM_OVER_NAV SPACE")
        self.assertRegex(SOURCE, r"#define NUM_OVER_NAV 3\b")
        self.assertGreater(
            list(LAYERS).index("number_over_nav"),
            list(LAYERS).index("layer_2"),
        )
        expected = [
            base if number == "&trans" else number
            for base, number in zip(LAYERS["default_layer"], LAYERS["layer_1"])
        ]
        self.assertEqual(LAYERS["number_over_nav"], expected)
        self.assertNotIn("&trans", LAYERS["number_over_nav"])
        # No permanent switch or toggle: &lt releases only its own layer.
        self.assertNotRegex(SOURCE, r"&(?:to|tog)\s+(?:NAV|NUM_OVER_NAV)\b")
        block = re.search(r"number_over_nav\s*\{(.*?)\};", SOURCE, re.S)[1]
        self.assertIn(
            "sensor-bindings = <&ec_ms_l SCRL_LEFT SCRL_RIGHT "
            "&ec_ms_r SCRL_DOWN SCRL_UP>;", block
        )

    def test_higher_layers_override_numbers_and_fall_back_after_release(self):
        # Static lookup model of ZMK's highest-active-layer precedence.
        # This does not emulate hold-tap timing or firmware press/release events.
        def resolve(active, position):
            names = list(LAYERS)
            for number in sorted(active | {0}, reverse=True):
                binding = LAYERS[names[number]][position]
                if binding != "&trans":
                    return binding
            self.fail(f"No binding for position {position}")

        active = {2, 3}
        self.assertEqual(resolve(active, 14), "&kp N2")
        self.assertEqual(resolve(active, 23), "&lt FN LANG2")
        self.assertEqual(resolve(active, 39), "&lt ALT ESC")
        self.assertEqual(resolve(active, 43), "&mo CONNECT")
        self.assertEqual(resolve(active | {4}, 1), "&kp F1")
        self.assertEqual(resolve(active | {4, 5}, 1), "&kp LA(Q)")
        self.assertEqual(resolve(active | {4, 5, 6}, 7), "&bt BT_SEL 0")
        # Once higher layers are off, the helper number layer is visible.
        self.assertEqual(resolve(active, 1), "&kp LS(N1)")
        # Releasing Space exposes NAV; releasing Enter too exposes BASE.
        self.assertEqual(resolve({2}, 14), "&kp LS(JP_LBKT)")
        self.assertEqual(resolve(set(), 14), "&kp S")

    def test_thumb_ime_and_security_keys(self):
        self.assertEqual(LAYERS["default_layer"][37], "&kp JP_ZKHK")
        self.assertEqual(
            LAYERS["default_layer"][42:44],
            ["&kp LC(LA(DEL))", "&mo CONNECT"],
        )
        for layer in ("layer_1", "layer_2", "layer_4", "layer_5",
                      "connection_layer"):
            for position in (37, 42):
                expected = ("&mo BOOT_ARM"
                            if layer == "connection_layer" and position == 37 else "&trans")
                self.assertEqual(LAYERS[layer][position], expected)

    def test_connection_layer_profile_keys_select_on_tap_and_peek_on_hold(self):
        connect = LAYERS["connection_layer"]
        self.assertEqual(
            connect[1:6], [f"&profile_key {n} {n}" for n in range(5)]
        )
        self.assertEqual(connect[7:12], [f"&bt BT_SEL {n}" for n in range(5)])
        hold_tap = re.search(r"profile_key:\s*\w+\s*\{(.*?)\};", SOURCE, re.S)[1]
        self.assertIn('flavor = "tap-preferred";', hold_tap)
        self.assertIn("tapping-term-ms = <350>;", hold_tap)
        self.assertIn("bindings = <&profile_status>, <&select_profile>;", hold_tap)
        select = re.search(r"select_profile:\s*\w+\s*\{(.*?)\};", SOURCE, re.S)[1]
        self.assertIn("bindings = <&macro_param_1to2>, <&bt BT_SEL 0>;", select)
        self.assertEqual(connect[27], "&conn_status")

    def test_bootloader_requires_a_hold_on_the_intended_half(self):
        connect = LAYERS["connection_layer"]
        self.assertEqual(connect[17:19], ["&trans"] * 2)
        self.assertEqual(connect[37], "&mo BOOT_ARM")
        self.assertEqual(connect[34:36], ["&bt BT_CLR_ALL", "&bt BT_CLR"])
        self.assertIn("if-layers = <CONNECT BOOT_ARM>;", SOURCE)
        self.assertIn("then-layer = <MAINTENANCE>;", SOURCE)
        self.assertEqual(LAYERS["boot_arm_layer"], ["&trans"] * 44)
        for layer, bindings in LAYERS.items():
            if layer == "maintenance_layer":
                self.assertEqual(
                    bindings,
                    ["&boot_hold 0 0" if i in (24, 35) else "&none" for i in range(44)],
                )
            else:
                self.assertNotIn("&boot_hold 0 0", bindings)
        boot = re.search(r"boot_hold:\s*\w+\s*\{(.*?)\};", SOURCE, re.S)[1]
        self.assertIn('flavor = "tap-preferred";', boot)
        self.assertIn("tapping-term-ms = <1000>;", boot)
        self.assertIn("hold-trigger-on-release;", boot)
        self.assertIn("hold-trigger-key-positions = <NO_PHYSICAL_KEY>;", boot)
        self.assertRegex(SOURCE, r"(?m)^#define NO_PHYSICAL_KEY 44$")
        self.assertIn("bindings = <&bootloader>, <&none>;", boot)
        self.assertNotRegex(SOURCE.split("keymap {", 1)[0], r"bindings = <&boot_hold\b")

    def test_right_status_indicator_does_not_share_led_with_widget(self):
        build = (ROOT / "build.yaml").read_text()
        shields = ROOT / "boards/shields/sosho"
        for variant in ("trackpad", "trackball"):
            with self.subTest(variant=variant):
                self.assertRegex(build, rf"(?m)^\s+shield: sosho_R_{variant}$")
                self.assertIn(f"shield: sosho_L_{variant} rgbled_adapter", build)
                right = (shields / f"sosho_R_{variant}.conf").read_text()
                self.assertIn("CONFIG_LED=y", right)
                self.assertIn("CONFIG_RGBLED_WIDGET=n", right)

    def test_left_trackpad_tap_click_enabled(self):
        overlay = (ROOT / "boards/shields/sosho/sosho_L_trackpad.overlay").read_text()
        block = re.search(r"&glidepoint\s*\{(.*?)\};", overlay, re.S)[1]
        self.assertIn('status = "okay";', block)
        self.assertIn("primary-tap-enable;", block)
        self.assertIn("invert-x;", block)

    def test_left_trackpad_and_right_trackball_processors(self):
        overlay = (ROOT / "boards/shields/sosho/sosho_R_trackball.overlay").read_text()
        for listener in ("glidepoint_split_listener", "trackball_listener"):
            block = re.search(
                rf"&{listener}\s*\{{(.*?\n\}};)", overlay, re.S
            )[1]
            base, scroller = block.split("scroller {", 1)
            self.assertIn("layers = <1 2 3>;", scroller)
            self.assertIn("<&zip_xy_to_scroll_mapper>", scroller)
            self.assertIn("<&zip_scroll_scaler 1 12>", scroller)
            self.assertNotIn("process-next;", scroller)
            scroll_transform = (
                "<&zip_scroll_transform "
                "(INPUT_TRANSFORM_X_INVERT | INPUT_TRANSFORM_Y_INVERT)>"
            )
            self.assertNotIn("zip_scroll_transform", base)
            self.assertLess(
                scroller.index("<&zip_xy_to_scroll_mapper>"),
                scroller.index(scroll_transform),
            )
            self.assertLess(
                scroller.index(scroll_transform),
                scroller.index("<&zip_scroll_scaler 1 12>"),
            )
            if listener == "glidepoint_split_listener":
                self.assertIn("<&zip_xy_scaler 2 1>", base)
                self.assertNotIn("zip_xy_scaler", scroller)
            else:
                self.assertIn("<&zip_xy_scaler 11 10>", base)
                self.assertNotIn("zip_xy_scaler", scroller)
                transform = (
                    "<&zip_xy_transform "
                    "(INPUT_TRANSFORM_X_INVERT | INPUT_TRANSFORM_Y_INVERT)>"
                )
                self.assertIn(transform, base)
                self.assertLess(
                    scroller.index(transform),
                    scroller.index("<&zip_xy_to_scroll_mapper>"),
                )

    def test_encoder_scroll_multiplier_does_not_change_volume_timing(self):
        for name in ("ec_ms_h", "ec_ms_v"):
            block = re.search(rf"{name}\s*\{{(.*?)\}};", SOURCE, re.S)[1]
            self.assertIn('compatible = "sosho,behavior-encoder-mouse-scroll";', block)
            self.assertIn("scroll-multiplier = <2>;", block)
        sensors = (ROOT / "boards/shields/sosho/sosho.dtsi").read_text()
        self.assertIn("triggers-per-rotation = <24>;", sensors)
        self.assertIn(
            "sensor-bindings = <&inc_dec_kp C_VOL_DN C_VOL_UP &ec_ms_r SCRL_DOWN SCRL_UP>;",
            SOURCE,
        )

    def test_local_encoder_behavior_is_registered_without_boot_delay(self):
        module = (ROOT / "zephyr/module.yml").read_text()
        self.assertIn("cmake: cmake", module)
        self.assertIn("dts_root: .", module)
        cmake = (ROOT / "cmake/CMakeLists.txt").read_text()
        self.assertIn("../src/behavior_encoder_mouse_scroll.c", cmake)
        self.assertNotIn("boot_delay_hack", cmake)


if __name__ == "__main__":
    unittest.main()
