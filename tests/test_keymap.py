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
            ["default_layer"] + [f"layer_{n}" for n in range(1, 5)]
            + ["connection_layer"],
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
                         "&bspc_del": 0}[behavior]
                        if behavior != "&bt"
                        else (2 if args[0] == "BT_SEL" else 1),
                    )

    def test_base_layout(self):
        expected = [
            "&kp F11", *[f"&kp {k}" for k in "QWERTYUIOP"], "&kp F12",
            "&mt LSHFT JP_COLON", *[f"&kp {k}" for k in "ASDFGHJKL"],
            "&mt LCTRL TAB", "&lt FN JP_ZKHK",
            "&kp LGUI", "&mt LSHFT Z", *[f"&kp {k}" for k in "XCVBNM"],
            "&kp COMMA", "&kp DOT", "&kp SLASH", "&kp LALT",
            "&kp LALT", "&kp LGUI", "&lt NUM SPACE", "&lt ALT ESC",
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
        for name, number in {"NUM": 1, "NAV": 2, "FN": 3,
                             "ALT": 4, "CONNECT": 5}.items():
            self.assertRegex(SOURCE, rf"#define {name} {number}\b")
        self.assertEqual(LAYERS["layer_1"][40], "&kp DEL")
        self.assertEqual(
            LAYERS["layer_2"][18:22],
            ["&kp LEFT", "&kp DOWN", "&kp UP", "&kp RIGHT"],
        )
        self.assertEqual(
            LAYERS["layer_3"][1:11], [f"&kp F{n}" for n in range(1, 11)]
        )
        self.assertEqual(LAYERS["layer_4"][41], "&kp LA(ENTER)")
        self.assertNotIn("NUM_ALT", SOURCE)

    def test_no_removed_mod_taps(self):
        self.assertNotRegex(SOURCE, r"&mt\s+\w+\s+(?:SLASH|LANG1|LANG2)\b")

    def test_z_hold_is_left_shift(self):
        self.assertEqual(LAYERS["default_layer"][25], "&mt LSHFT Z")
        for layer in ("layer_3", "connection_layer"):
            self.assertEqual(LAYERS[layer][25], "&trans")

    def test_tapping_term(self):
        for behavior in ("mt", "lt"):
            self.assertRegex(
                SOURCE,
                rf'&{behavior}\s*\{{\s*flavor = "tap-preferred";'
                r"\s*tapping-term-ms = <180>;",
            )

    def test_quick_tap_does_not_force_repeat(self):
        for behavior in ("mt", "lt"):
            block = re.search(rf"&{behavior}\s*\{{(.*?)\}};", SOURCE, re.S)[1]
            self.assertIn("quick-tap-ms = <0>;", block)

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
        for layer in ("layer_2", "layer_3", "layer_4", "connection_layer"):
            self.assertEqual(LAYERS[layer][40], "&trans")

    def test_revised_outer_keys(self):
        base = LAYERS["default_layer"]
        self.assertEqual(base[12], "&mt LSHFT JP_COLON")
        self.assertEqual(base[23], "&lt FN JP_ZKHK")
        self.assertEqual(base[24], "&kp LGUI")
        self.assertEqual(base[35], "&kp LALT")
        self.assertNotRegex(SOURCE, r"\bLANG[12]\b")
        for layer in ("layer_1", "layer_2", "layer_3", "layer_4",
                      "connection_layer"):
            for position in (12, 23, 24, 35):
                expected = (
                    "&bt BT_CLR"
                    if layer == "connection_layer" and position == 35
                    else "&trans"
                )
                self.assertEqual(LAYERS[layer][position], expected)

    def test_ctrl_alt_delete_next_to_connection_key(self):
        self.assertEqual(
            LAYERS["default_layer"][42:44],
            ["&kp LC(LA(DEL))", "&mo CONNECT"],
        )
        for layer in ("layer_1", "layer_2", "layer_3", "layer_4",
                      "connection_layer"):
            self.assertEqual(LAYERS[layer][42], "&trans")

    def test_left_trackpad_and_right_trackball_processors(self):
        overlay = (ROOT / "boards/shields/sosho/sosho_R_trackball.overlay").read_text()
        for listener in ("glidepoint_split_listener", "trackball_listener"):
            block = re.search(
                rf"&{listener}\s*\{{(.*?\n\}};)", overlay, re.S
            )[1]
            base, scroller = block.split("scroller {", 1)
            self.assertIn("layers = <1 2>;", scroller)
            self.assertIn("<&zip_xy_to_scroll_mapper>", scroller)
            self.assertIn("<&zip_scroll_scaler 1 16>", scroller)
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
                scroller.index("<&zip_scroll_scaler 1 16>"),
            )
            if listener == "glidepoint_split_listener":
                self.assertIn("<&zip_xy_scaler 2 1>", base)
                self.assertNotIn("zip_xy_scaler", scroller)
            else:
                transform = (
                    "<&zip_xy_transform "
                    "(INPUT_TRANSFORM_X_INVERT | INPUT_TRANSFORM_Y_INVERT)>"
                )
                self.assertIn(transform, base)
                self.assertLess(
                    scroller.index(transform),
                    scroller.index("<&zip_xy_to_scroll_mapper>"),
                )


if __name__ == "__main__":
    unittest.main()
