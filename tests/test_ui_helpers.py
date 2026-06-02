import unittest
import inspect
import math

import main


class UIHelperTest(unittest.TestCase):
    def test_blend_color_interpolates_rgb_channels(self):
        self.assertEqual(main.blend_color((0, 0, 0), (100, 50, 200), 0.25), (25, 12, 50))

    def test_blend_color_clamps_ratio(self):
        self.assertEqual(main.blend_color((10, 20, 30), (20, 40, 60), -1), (10, 20, 30))
        self.assertEqual(main.blend_color((10, 20, 30), (20, 40, 60), 2), (20, 40, 60))

    def test_hex_to_rgb_accepts_shared_palette_values(self):
        self.assertEqual(main.hex_to_rgb("#214365"), (33, 67, 101))
        self.assertEqual(main.hex_to_rgb("d49a31"), (212, 154, 49))

    def test_visible_ticket_render_state_keeps_back_side_continuous(self):
        self.assertEqual(main.visible_ticket_render_state(0), (True, 0))
        self.assertEqual(main.visible_ticket_render_state(math.pi), (False, 0))
        self.assertAlmostEqual(main.visible_ticket_render_state(math.pi - 0.05)[1], -0.05)
        self.assertAlmostEqual(main.visible_ticket_render_state(-math.pi + 0.05)[1], 0.05)

    def test_ticket_flat_render_state_matches_small_rotation_snap(self):
        self.assertTrue(main.ticket_uses_flat_render(0.05, 0.02))
        self.assertFalse(main.ticket_uses_flat_render(0.4, 0.02))

    def test_flat_ticket_source_mapping_uses_actual_scaled_rect(self):
        source_size = (627, 921)
        viewport_size = (930, 780)
        zoom = 0.73
        left, top, display_width, display_height = main.flat_ticket_display_rect(source_size, zoom, viewport_size)
        source_point = (410, 512)
        screen_pos = (
            left + int(source_point[0] * display_width / source_size[0]),
            top + int(source_point[1] * display_height / source_size[1]),
        )

        mapped = main.screen_to_flat_ticket_source_point(screen_pos, source_size, zoom, viewport_size)

        self.assertLessEqual(abs(mapped[0] - source_point[0]), 1)
        self.assertLessEqual(abs(mapped[1] - source_point[1]), 1)

    def test_screen_to_ticket_source_point_tracks_current_zoom(self):
        source_size = (1000, 500)
        viewport_size = (930, 780)
        zoom = 1.2
        source_point = (250, 100)
        screen_pos = (
            int(viewport_size[0] / 2 - source_size[0] * zoom / 2 + source_point[0] * zoom),
            int(viewport_size[1] / 2 - source_size[1] * zoom / 2 + source_point[1] * zoom),
        )

        self.assertEqual(
            main.screen_to_ticket_source_point(screen_pos, source_size, zoom, 0.0, 0.0, viewport_size),
            source_point,
        )

    def test_clean_placeholder_value_treats_placeholder_as_empty(self):
        self.assertEqual(main.clean_placeholder_value("邮箱可不填", "邮箱可不填"), "")
        self.assertEqual(main.clean_placeholder_value("  dana@example.com  ", "邮箱可不填"), "dana@example.com")

    def test_ticket_style_selector_uses_clickable_dropdown(self):
        source = inspect.getsource(main.choose_ticket_selection)

        self.assertIn("ttk.Combobox", source)
        self.assertNotIn("tk.Listbox", source)

    def test_login_password_visibility_uses_inline_eye_control(self):
        source = inspect.getsource(main.create_login_register_window)

        self.assertIn("set_visibility_control", source)
        self.assertIn("ModernTkCheck", source)
        self.assertNotIn('"显示密码"', source)

    def test_selector_keeps_action_buttons_inside_visible_card(self):
        source = inspect.getsource(main.choose_ticket_selection)

        self.assertIn("window_width, window_height = 780, 700", source)
        self.assertIn("height=546", source)
        self.assertIn("开始刮奖", source)

    def test_game_page_exposes_reselect_control(self):
        source = inspect.getsource(main.main_game)

        self.assertIn("重新选择", source)
        self.assertIn("\"reselect\"", source)
        self.assertIn("本地模拟票面", source)
        self.assertIn("summarize_game_rule", source)
        self.assertIn("selector_text_bottom", source)
        self.assertIn("max_height", source)
        self.assertIn("info_scroll_offset", source)
        self.assertIn("pygame.MOUSEWHEEL", source)
        self.assertIn("正在生成票面", source)
        self.assertIn("draw_rotated_ticket", source)
        self.assertIn("screen_to_ticket_point", source)
        self.assertIn("crop_ticket_surfaces", source)
        self.assertIn("adjust_ticket_zoom", source)
        self.assertIn("TICKET_ROTATION_SENSITIVITY", source)
        self.assertIn("TICKET_ZOOM_MAX", source)
        self.assertIn("TICKET_RENDER_SCALE", source)
        self.assertNotIn("刮奖区原图", source)
        self.assertNotIn("本地生成刮奖区", source)

    def test_game_rule_summary_removes_redundant_scratch_wording(self):
        summary = main.summarize_game_rule(
            "刮开覆盖膜，如果出现奖金标志，即中得该奖金。\n中奖奖金兼中兼得。",
            max_chars=40,
        )

        self.assertEqual(summary, "如果出现奖金标志，即中得该奖金")

    def test_selection_flow_reopens_selector_after_game_reselect(self):
        original_choose = main.choose_ticket_selection
        original_main_game = main.main_game
        calls = []
        selections = [
            main.TicketSelection(face_value=10, product_name="骏马贺岁（本地模拟）"),
            main.TicketSelection(face_value=20, product_name="马到成功（本地模拟）"),
        ]
        game_results = ["reselect", None]
        try:
            def fake_choose(username, initial_face_value=main.TICKET_PRICE):
                calls.append((username, initial_face_value))
                return selections.pop(0)

            def fake_main_game(username, _balance=None, face_value=main.TICKET_PRICE, ticket_id=None, theme_index=0):
                self.assertEqual(username, "switcher")
                return game_results.pop(0)

            main.choose_ticket_selection = fake_choose
            main.main_game = fake_main_game

            main.run_ticket_selection_flow("switcher")

            self.assertEqual(calls, [("switcher", main.TICKET_PRICE), ("switcher", 10)])
        finally:
            main.choose_ticket_selection = original_choose
            main.main_game = original_main_game

    def test_celebration_particles_spray_from_both_sides_toward_center(self):
        rng = main.random.Random(20260529)

        particles = main.build_celebration_particles(840, 780, rng)

        self.assertEqual(len(particles), main.FIREWORK_PARTICLE_COUNT_PER_SIDE * 2)
        left_particles = [particle for particle in particles if particle.side == "left"]
        right_particles = [particle for particle in particles if particle.side == "right"]
        self.assertEqual(len(left_particles), main.FIREWORK_PARTICLE_COUNT_PER_SIDE)
        self.assertEqual(len(right_particles), main.FIREWORK_PARTICLE_COUNT_PER_SIDE)
        self.assertTrue(all(particle.vx > 0 for particle in left_particles))
        self.assertTrue(all(particle.vx < 0 for particle in right_particles))
        self.assertTrue(all(0 <= particle.birth_delay_ms < main.FIREWORK_DURATION_MS for particle in particles))
        self.assertTrue(all(particle.life_ms <= main.FIREWORK_DURATION_MS for particle in particles))


if __name__ == "__main__":
    unittest.main()
