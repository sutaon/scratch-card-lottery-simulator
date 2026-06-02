import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

import main


class AccountLogicTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.user_file = self.data_dir / "UserData.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def read_users(self):
        return json.loads(self.user_file.read_text(encoding="utf-8"))

    def test_register_login_and_charge_flow(self):
        registered = main.register_account("alice", "abc123", self.user_file)
        self.assertEqual(registered["balance"], 200)
        self.assertIn("password_hash", registered)
        self.assertNotIn("password", registered)

        authenticated = main.authenticate_account("alice", "abc123", self.user_file)
        self.assertEqual(authenticated["balance"], 200)

        balance = main.charge_scratch_card("alice", self.user_file)
        self.assertEqual(balance, 190)
        self.assertEqual(self.read_users()[0]["balance"], 190)

    def test_website_face_values_are_available(self):
        self.assertEqual(main.LOTTERY_FACE_VALUES, (2, 3, 5, 10, 20, 30, 50))
        self.assertEqual(set(main.TICKET_TYPES), set(main.LOTTERY_FACE_VALUES))

    def test_ticket_style_options_only_expose_local_simulation(self):
        for face_value in main.LOTTERY_FACE_VALUES:
            options = main.ticket_style_options(face_value)

            self.assertEqual(len(options), 1)
            self.assertEqual(options[0].face_value, face_value)
            self.assertIsNone(options[0].ticket_id)
            self.assertIn("本地模拟", options[0].product_name)

    def test_charge_uses_selected_face_value(self):
        main.register_account("price", "abc123", self.user_file)

        balance = main.charge_scratch_card("price", self.user_file, face_value=50)

        self.assertEqual(balance, 150)
        self.assertEqual(self.read_users()[0]["balance"], 150)

    def test_charge_rejects_unsupported_face_value(self):
        main.register_account("invalid", "abc123", self.user_file)

        with self.assertRaises(ValueError):
            main.charge_scratch_card("invalid", self.user_file, face_value=7)

    def test_register_accepts_optional_email_and_confirm_password(self):
        registered = main.register_account(
            "dana",
            "abc123",
            self.user_file,
            email="dana@example.com",
            confirm_password="abc123",
        )

        self.assertEqual(registered["email"], "dana@example.com")
        self.assertEqual(self.read_users()[0]["email"], "dana@example.com")

    def test_register_allows_blank_email(self):
        registered = main.register_account(
            "eric",
            "abc123",
            self.user_file,
            email="",
            confirm_password="abc123",
        )

        self.assertEqual(registered["email"], "")

    def test_login_preferences_remember_username_and_optional_password(self):
        prefs_file = self.data_dir / "LoginPreferences.json"

        main.save_login_preferences("alice", False, "abc123", prefs_file)
        prefs = main.load_login_preferences(prefs_file)
        self.assertEqual(prefs["username"], "alice")
        self.assertFalse(prefs["remember_password"])
        self.assertEqual(prefs["password"], "")

        main.save_login_preferences("alice", True, "abc123", prefs_file)
        prefs = main.load_login_preferences(prefs_file)
        self.assertTrue(prefs["remember_password"])
        self.assertEqual(prefs["password"], "")
        self.assertNotIn("abc123", prefs_file.read_text(encoding="utf-8"))

    def test_authenticate_upgrades_legacy_plaintext_password(self):
        self.user_file.write_text(
            json.dumps(
                [{"UID": "1", "username": "legacy", "password": "pw123", "balance": 5}],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        user = main.authenticate_account("legacy", "pw123", self.user_file)
        stored = self.read_users()[0]

        self.assertEqual(user["username"], "legacy")
        self.assertIn("password_hash", stored)
        self.assertNotIn("password", stored)

    def test_register_rejects_mismatched_confirm_password(self):
        with self.assertRaises(main.AuthenticationError):
            main.register_account(
                "frank",
                "abc123",
                self.user_file,
                email="frank@example.com",
                confirm_password="abc124",
            )

    def test_charge_rejects_low_balance_without_mutating(self):
        self.user_file.write_text(
            json.dumps(
                [{"UID": "1", "username": "bob", "password": "pw", "balance": 5}],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with self.assertRaises(main.InsufficientBalanceError):
            main.charge_scratch_card("bob", self.user_file)

        self.assertEqual(self.read_users()[0]["balance"], 5)

    def test_reward_can_only_be_claimed_once_per_ticket(self):
        self.user_file.write_text(
            json.dumps(
                [{"UID": "1", "username": "cai", "password": "pw", "balance": 90}],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = main.TicketState(prize=50)

        first_balance = main.claim_ticket_prize("cai", state, self.user_file)
        second_balance = main.claim_ticket_prize("cai", state, self.user_file)

        self.assertEqual(first_balance, 140)
        self.assertEqual(second_balance, 140)
        self.assertEqual(self.read_users()[0]["balance"], 140)

    def test_prize_weights_keep_large_prizes_rare(self):
        weights = dict(main.PRIZE_WEIGHTS)

        self.assertEqual(sum(weights.values()), 100000)
        self.assertGreater(weights["20"], weights["600"])
        self.assertGreater(weights["600"], weights["10,000"])
        self.assertGreater(weights["10,000"], weights["250,000"])

    def test_prize_weights_cover_all_face_values(self):
        for face_value in main.LOTTERY_FACE_VALUES:
            weights = main.get_prize_weights(face_value)
            self.assertEqual(sum(weight for _amount, weight in weights), main.PRIZE_WEIGHT_TOTAL)
            self.assertGreaterEqual(min(main.normalize_money(amount) for amount, _weight in weights), face_value)

    def test_win_chance_is_lowered(self):
        self.assertLess(main.WIN_CHANCE, 0.08)

    def test_weighted_prize_choice_uses_pseudorandom_boundaries(self):
        class FixedRandom:
            def __init__(self, value):
                self.value = value

            def random(self):
                return self.value

        self.assertEqual(main.choose_prize_key(FixedRandom(0.0)), "20")
        self.assertEqual(main.choose_prize_key(FixedRandom(0.999995)), "250,000")

    def test_ticket_number_choice_accepts_seeded_pseudorandom_source(self):
        valid_numbers = [f"{number:02d}" for number in range(100)]
        first_rng = main.random.Random(20260526)
        second_rng = main.random.Random(20260526)

        first = main.choose_ticket_numbers(valid_numbers, first_rng)
        second = main.choose_ticket_numbers(valid_numbers, second_rng)
        play_numbers, win_numbers = first
        match_count = len(set(play_numbers) & set(win_numbers))

        self.assertEqual(first, second)
        self.assertIn(match_count, (0, 1, 2))
        self.assertEqual(len(play_numbers), 10)
        self.assertEqual(len(win_numbers), 2)

    def test_winning_marker_rects_cover_matching_play_numbers(self):
        ticket = main.TicketState(
            prize=600,
            play_numbers=["01", "02", "03", "04", "05", "06", "07", "08", "09", "10"],
            win_numbers=["03", "09"],
        )

        rects = main.build_win_marker_rects(ticket)

        self.assertEqual(len(rects), 2)
        self.assertEqual(rects[0][0], main.PLAY_COORDINATES[2][0] - 34)
        self.assertEqual(rects[0][1], main.PLAY_COORDINATES[2][1] - 6)
        self.assertEqual(rects[1][0], main.PLAY_COORDINATES[8][0] - 34)
        self.assertEqual(rects[1][1], main.PLAY_COORDINATES[8][1] - 6)

    def test_smoke_test_generates_ticket_with_runtime_paths(self):
        ticket_file = self.data_dir / "ticket.png"
        original_user_data_file = main.default_user_data_file
        original_ticket_output_file = main.default_ticket_output_file
        try:
            main.default_user_data_file = lambda: self.user_file
            main.default_ticket_output_file = lambda: ticket_file

            exit_code = main.run_smoke_test()

            self.assertEqual(exit_code, 0)
            self.assertTrue(self.user_file.exists())
            self.assertTrue(ticket_file.exists())
            self.assertGreater(ticket_file.stat().st_size, 0)
        finally:
            main.default_user_data_file = original_user_data_file
            main.default_ticket_output_file = original_ticket_output_file

    def test_ticket_generation_accepts_every_face_value(self):
        original_ticket_output_file = main.default_ticket_output_file
        try:
            for face_value in main.LOTTERY_FACE_VALUES:
                ticket_file = self.data_dir / f"ticket-{face_value}.png"
                main.default_ticket_output_file = lambda path=ticket_file: path

                output, prize, play_numbers, win_numbers = main.generate_scratch_card(face_value=face_value)

                self.assertEqual(Path(output), ticket_file)
                self.assertTrue(ticket_file.exists())
                self.assertGreater(ticket_file.stat().st_size, 0)
                self.assertGreaterEqual(prize, 0)
                self.assertEqual(len(play_numbers), 10)
                self.assertEqual(len(win_numbers), 2)
        finally:
            main.default_ticket_output_file = original_ticket_output_file

    def test_ticket_visual_uses_local_simulation_even_when_official_assets_available(self):
        base_file = self.data_dir / "local-base.png"
        cover_file = self.data_dir / "local-cover.png"
        ticket_file = self.data_dir / "local-ticket.png"
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_ticket_output_file = main.default_ticket_output_file
        try:
            main.default_ticket_base_file = lambda: base_file
            main.default_ticket_cover_file = lambda: cover_file
            main.default_ticket_output_file = lambda: ticket_file

            visual = main.generate_ticket_visual(50, main.random.Random(20260530), ticket_id=105)

            self.assertEqual(visual.visual_style, "legacy")
            self.assertEqual(visual.face_value, 50)
            self.assertEqual(visual.product_name, main.get_ticket_type(50).name)
            self.assertIsNone(visual.ticket_id)
            self.assertTrue(base_file.exists())
            self.assertTrue(cover_file.exists())
            self.assertTrue(ticket_file.exists())
            self.assertTrue(Path(visual.back_path).exists())
            self.assertGreater(base_file.stat().st_size, 0)
            self.assertGreater(cover_file.stat().st_size, 0)
            self.assertGreater(visual.scratch_rect[2], 0)
            self.assertGreater(visual.scratch_rect[3], 0)
        finally:
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            main.default_ticket_output_file = original_ticket_output_file

    def test_local_simulation_uses_official_back_original(self):
        base_file = self.data_dir / "local-base.png"
        cover_file = self.data_dir / "local-cover.png"
        ticket_file = self.data_dir / "local-ticket.png"
        back_file = self.data_dir / "local-back.png"
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_ticket_output_file = main.default_ticket_output_file
        original_back_file = main.default_ticket_back_output_file
        try:
            main.default_ticket_base_file = lambda: base_file
            main.default_ticket_cover_file = lambda: cover_file
            main.default_ticket_output_file = lambda: ticket_file
            main.default_ticket_back_output_file = lambda: back_file

            visual = main.generate_ticket_visual(10, target_size=(520, 780))

            with Image.open(visual.back_path).convert("RGB") as generated:
                with Image.open(main.default_ticket_back_file()).convert("RGB") as expected:
                    self.assertIsNone(ImageChops.difference(generated, expected).getbbox())
        finally:
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            main.default_ticket_output_file = original_ticket_output_file
            main.default_ticket_back_output_file = original_back_file

    def test_official_winning_visual_uses_generated_clean_middle_without_sample_art(self):
        base_file = self.data_dir / "winning-base.png"
        cover_file = self.data_dir / "winning-cover.png"
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_win_chance = main.WIN_CHANCE
        try:
            main.default_ticket_base_file = lambda: base_file
            main.default_ticket_cover_file = lambda: cover_file
            main.WIN_CHANCE = 1.0

            ticket = main.find_official_ticket(208)
            sample_base, sample_cover, expected_rect = main.compose_ticket_sections(
                ticket,
                ticket["themes"][0],
                "awardImg",
            )
            visual = main.generate_official_ticket_visual(
                10,
                main.random.Random(20260531),
                ticket_id=208,
                base_output_path=base_file,
                cover_output_path=cover_file,
            )

            self.assertIsNotNone(visual)
            self.assertGreater(visual.prize, 0)
            self.assertGreater(len(visual.play_numbers), 0)
            self.assertEqual(visual.win_numbers, [])
            with Image.open(base_file).convert("RGBA") as actual_base:
                self.assertIsNotNone(ImageChops.difference(actual_base.convert("RGB"), sample_base.convert("RGB")).getbbox())
            with Image.open(cover_file).convert("RGBA") as actual_cover:
                self.assertIsNotNone(ImageChops.difference(actual_cover.convert("RGB"), sample_cover.convert("RGB")).getbbox())
            self.assertEqual(visual.scratch_rect, expected_rect)
        finally:
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            main.WIN_CHANCE = original_win_chance

    def test_official_ticket_frame_parts_preserve_downloaded_header_footer(self):
        ticket = main.find_official_ticket(208)
        theme = ticket["themes"][0]

        top, bottom = main.official_ticket_frame_parts(ticket, theme, (520, 283))

        with Image.open(main.resource_path(theme["backgroundA"])).convert("RGBA") as expected_top:
            self.assertIsNone(ImageChops.difference(top.convert("RGBA"), expected_top).getbbox())
        with Image.open(main.resource_path(theme["backgroundC"])).convert("RGBA") as expected_bottom:
            self.assertIsNone(ImageChops.difference(bottom.convert("RGBA"), expected_bottom).getbbox())

    def test_horizontal_ticket_scratches_only_revealed_front_area(self):
        base_file = self.data_dir / "wide-base.png"
        cover_file = self.data_dir / "wide-cover.png"

        visual = main.generate_official_ticket_visual(
            50,
            main.random.Random(20260601),
            ticket_id=211,
            base_output_path=base_file,
            cover_output_path=cover_file,
            target_size=(930, 780),
        )

        self.assertLess(visual.scratch_rect[2], 700)
        self.assertEqual(visual.scratch_rect[3], 290)
        with Image.open(cover_file).convert("RGB") as cover:
            right_panel = cover.crop((650, visual.scratch_rect[1], 920, visual.scratch_rect[1] + visual.scratch_rect[3]))
            average = right_panel.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))

        self.assertGreater(sum(average) / 3, 170)

    def test_official_ticket_visual_randomizes_generated_reveal_middle(self):
        base_file_a = self.data_dir / "generated-a-base.png"
        cover_file_a = self.data_dir / "generated-a-cover.png"
        base_file_b = self.data_dir / "generated-b-base.png"
        cover_file_b = self.data_dir / "generated-b-cover.png"
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_win_chance = main.WIN_CHANCE
        try:
            main.WIN_CHANCE = 0.0

            visual_a = main.generate_official_ticket_visual(
                50,
                main.random.Random(20260531),
                ticket_id=211,
                base_output_path=base_file_a,
                cover_output_path=cover_file_a,
            )
            visual_b = main.generate_official_ticket_visual(
                50,
                main.random.Random(20260530),
                ticket_id=211,
                base_output_path=base_file_b,
                cover_output_path=cover_file_b,
            )

            self.assertIsNotNone(visual_a)
            self.assertIsNotNone(visual_b)
            self.assertEqual(visual_a.scratch_rect, visual_b.scratch_rect)
            self.assertGreater(len(visual_a.play_numbers), 0)
            self.assertGreater(len(visual_b.play_numbers), 0)

            with Image.open(base_file_a).convert("RGBA") as image_a, Image.open(base_file_b).convert("RGBA") as image_b:
                rect = visual_a.scratch_rect
                crop_a = image_a.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
                crop_b = image_b.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
                self.assertIsNotNone(ImageChops.difference(crop_a.convert("RGB"), crop_b.convert("RGB")).getbbox())
        finally:
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            main.WIN_CHANCE = original_win_chance

    def test_prize_amount_ticket_uses_amount_reveal_without_number_match(self):
        ticket = main.find_official_ticket(207)
        with Image.open(main.resource_path(ticket["themes"][0]["notAwardImg"])) as reference:
            _image, _cover, play_tokens, win_numbers = main.draw_generated_middle(
                reference.size,
                ticket,
                30,
                main.random.Random(20260531),
                reference=reference,
            )

        self.assertEqual(win_numbers, [])
        self.assertTrue(play_tokens)
        self.assertTrue(all(token.startswith("￥") for token in play_tokens), ticket["name"])

    def test_jie_hao_yun_50_ticket_uses_all_number_layout(self):
        ticket = main.find_official_ticket(177)
        with Image.open(main.resource_path(ticket["themes"][0]["notAwardImg"])) as reference:
            _image, _cover, play_tokens, win_numbers = main.draw_generated_middle(
                reference.size,
                ticket,
                50,
                main.random.Random(20260601),
                reference=reference,
            )

        self.assertEqual(len(win_numbers), 3)
        self.assertEqual(len(play_tokens), 40)
        self.assertEqual(main.jie_hao_yun_play_count(ticket), 35)
        self.assertEqual(main.jie_hao_yun_all_symbol(ticket), "运")

    def test_wide_official_middle_uses_grey_ticket_print_style(self):
        ticket = main.find_official_ticket(211)
        with Image.open(main.resource_path(ticket["themes"][0]["backgroundB"])) as reference:
            reference_size = reference.size

        image, _cover, _play_numbers, _win_numbers = main.draw_generated_middle(
            reference_size,
            ticket,
            50,
            main.random.Random(20260531),
            (185, 42, 36),
        )

        sample = image.convert("RGB").resize((max(1, image.width // 3), max(1, image.height // 3)))
        pixels = [sample.getpixel((x, y)) for y in range(sample.height) for x in range(sample.width)]
        colorful_pixels = [pixel for pixel in pixels if max(pixel) - min(pixel) > 35]

        self.assertLess(len(colorful_pixels) / len(pixels), 0.08)

    def test_official_scratch_layout_classifies_representative_templates(self):
        examples = {
            2: "vertical-list",
            4: "wide-match",
            105: "tall-sheet",
            147: "wide-bonus-strip",
            208: "paired-symbol-prize",
            209: "compact-grid",
            211: "wide-symbol-grid",
        }

        for ticket_id, expected_kind in examples.items():
            ticket = main.find_official_ticket(ticket_id)
            with Image.open(main.resource_path(ticket["themes"][0]["notAwardImg"])) as reference:
                layout = main.official_scratch_layout(ticket, reference.size)

            self.assertEqual(layout.kind, expected_kind, ticket["name"])

    def test_reference_middle_background_discards_old_ticket_result_artifacts(self):
        examples = (2, 105)

        for ticket_id in examples:
            ticket = main.find_official_ticket(ticket_id)
            with Image.open(main.resource_path(ticket["themes"][0]["notAwardImg"])) as reference:
                background = main.build_reference_middle_background(reference.size, reference)

            sample = background.convert("RGB").resize((max(1, background.width // 4), max(1, background.height // 4)))
            pixels = [sample.getpixel((x, y)) for y in range(sample.height) for x in range(sample.width)]
            colorful_pixels = [pixel for pixel in pixels if max(pixel) - min(pixel) > 35]
            dark_pixels = [pixel for pixel in pixels if max(pixel) < 110]

            self.assertLess(len(colorful_pixels) / len(pixels), 0.08, ticket["name"])
            self.assertLess(len(dark_pixels) / len(pixels), 0.01, ticket["name"])

    def test_zodiac_paired_symbol_entries_follow_ticket_specific_prize_rule(self):
        examples = {185: "龙", 192: "蛇", 208: "马"}

        for ticket_id, symbol in examples.items():
            ticket = main.find_official_ticket(ticket_id)
            with Image.open(main.resource_path(ticket["themes"][0]["notAwardImg"])) as reference:
                layout = main.official_scratch_layout(ticket, reference.size)
            self.assertEqual(layout.kind, "paired-symbol-prize", ticket["name"])

            scenes = main.build_paired_symbol_prize_entries(ticket, 30, main.random.Random(20260531))

            self.assertEqual(len(scenes), 12)
            self.assertTrue(all(len(scene["symbols"]) == 3 for scene in scenes))
            winning_scenes = [scene for scene in scenes if scene["matched"]]
            self.assertEqual(len(winning_scenes), 1)
            winner = winning_scenes[0]
            matching_symbol_count = winner["symbols"].count(symbol)
            lamp_count = winner["symbols"].count("灯笼")
            self.assertTrue(matching_symbol_count >= 2 or lamp_count >= 1, ticket["name"])
            if matching_symbol_count >= 2:
                self.assertEqual(winner["amount"], 30)
            else:
                self.assertEqual(winner["amount"] * 3, 30)

            losing_scenes = main.build_paired_symbol_prize_entries(ticket, 0, main.random.Random(20260531))

            self.assertTrue(
                all(scene["symbols"].count(symbol) < 2 and "灯笼" not in scene["symbols"] for scene in losing_scenes),
                ticket["name"],
            )

    def test_symbol_prize_tickets_generate_symbol_tokens_instead_of_number_match(self):
        examples = {209: "马", 114: "锦鲤"}

        for ticket_id, expected_symbol in examples.items():
            ticket = main.find_official_ticket(ticket_id)
            with Image.open(main.resource_path(ticket["themes"][0]["notAwardImg"])) as reference:
                _image, _cover, play_tokens, win_numbers = main.draw_generated_middle(
                    reference.size,
                    ticket,
                    int(ticket.get("money", 10)),
                    main.random.Random(20260531),
                    reference=reference,
                )

            self.assertEqual(win_numbers, [], ticket["name"])
            self.assertIn(expected_symbol, play_tokens, ticket["name"])

    def test_symbol_prize_rule_parser_ignores_generic_multiplier_wording(self):
        ticket = main.find_official_ticket(204)

        symbols = [spec["symbol"] for spec in main.symbol_prize_specs(ticket)]

        self.assertEqual(symbols, ["出彩", "2倍", "5倍"])

    def test_ticket_visual_falls_back_for_face_values_without_official_assets(self):
        base_file = self.data_dir / "legacy-base.png"
        cover_file = self.data_dir / "legacy-cover.png"
        ticket_file = self.data_dir / "legacy-ticket.png"
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_ticket_output_file = main.default_ticket_output_file
        try:
            main.default_ticket_base_file = lambda: base_file
            main.default_ticket_cover_file = lambda: cover_file
            main.default_ticket_output_file = lambda: ticket_file

            visual = main.generate_ticket_visual(2, main.random.Random(20260530))

            self.assertEqual(visual.visual_style, "legacy")
            self.assertEqual(visual.face_value, 2)
            self.assertTrue(base_file.exists())
            self.assertTrue(cover_file.exists())
            self.assertTrue(ticket_file.exists())
            self.assertTrue(Path(visual.back_path).exists())
        finally:
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            main.default_ticket_output_file = original_ticket_output_file

    def test_official_layout_one_ticket_composes_to_game_size(self):
        ticket = next(ticket for ticket in main.load_official_ticket_catalog() if ticket["id"] == 8)

        base, cover, scratch_rect = main.compose_ticket_sections(ticket, ticket["themes"][0], "notAwardImg")

        self.assertEqual(base.size, (520, 780))
        self.assertEqual(cover.size, (520, 780))
        self.assertGreater(scratch_rect[2], 0)
        self.assertGreater(scratch_rect[3], 0)

    def test_frozen_dist_runtime_root_uses_project_parent_data(self):
        project_dir = self.data_dir / "Lottery ticket"
        dist_dir = project_dir / "dist"
        (project_dir / "Datarecourses").mkdir(parents=True)
        dist_dir.mkdir(parents=True)

        original_executable = sys.executable
        had_frozen = hasattr(sys, "frozen")
        original_frozen = getattr(sys, "frozen", None)
        try:
            sys.executable = str(dist_dir / "彩票刮刮乐.exe")
            sys.frozen = True

            self.assertEqual(main.runtime_root(), project_dir)
        finally:
            sys.executable = original_executable
            if had_frozen:
                sys.frozen = original_frozen
            else:
                delattr(sys, "frozen")


if __name__ == "__main__":
    unittest.main()
