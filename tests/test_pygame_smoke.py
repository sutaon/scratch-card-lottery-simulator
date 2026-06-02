import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import main


class PygameSmokeTest(unittest.TestCase):
    def test_game_initializes_and_charges_selected_face_value(self):
        import pygame

        temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(temp_dir.name)
        user_file = data_dir / "UserData.json"
        base_file = data_dir / "ticket-base.png"
        cover_file = data_dir / "ticket-cover.png"

        original_user_data_file = main.default_user_data_file
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_event_get = pygame.event.get
        try:
            main.default_user_data_file = lambda: user_file
            main.default_ticket_base_file = lambda: base_file
            main.default_ticket_cover_file = lambda: cover_file
            main.register_account("smoke", "abc123", user_file)

            sent = {"quit": False}

            def fake_event_get():
                if sent["quit"]:
                    return []
                sent["quit"] = True
                return [pygame.event.Event(pygame.QUIT)]

            pygame.event.get = fake_event_get
            main.main_game("smoke", face_value=30)

            user = json.loads(user_file.read_text(encoding="utf-8"))[0]
            self.assertEqual(user["balance"], 170)
            self.assertTrue(base_file.exists())
            self.assertTrue(cover_file.exists())
            self.assertGreater(base_file.stat().st_size, 0)
            self.assertGreater(cover_file.stat().st_size, 0)
        finally:
            pygame.event.get = original_event_get
            main.default_user_data_file = original_user_data_file
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            temp_dir.cleanup()

    def test_game_reselect_button_returns_to_selection_flow(self):
        import pygame

        temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(temp_dir.name)
        user_file = data_dir / "UserData.json"
        base_file = data_dir / "ticket-base.png"
        cover_file = data_dir / "ticket-cover.png"

        original_user_data_file = main.default_user_data_file
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_event_get = pygame.event.get
        try:
            main.default_user_data_file = lambda: user_file
            main.default_ticket_base_file = lambda: base_file
            main.default_ticket_cover_file = lambda: cover_file
            main.register_account("switch", "abc123", user_file)

            sent = {"clicked": False}

            def fake_event_get():
                if sent["clicked"]:
                    return []
                sent["clicked"] = True
                return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (1090, 644)})]

            pygame.event.get = fake_event_get

            result = main.main_game("switch", face_value=10)

            self.assertEqual(result, "reselect")
        finally:
            pygame.event.get = original_event_get
            main.default_user_data_file = original_user_data_file
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            temp_dir.cleanup()

    def test_game_accepts_centered_3d_rotation_drag(self):
        import pygame

        temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(temp_dir.name)
        user_file = data_dir / "UserData.json"
        base_file = data_dir / "ticket-base.png"
        cover_file = data_dir / "ticket-cover.png"

        original_user_data_file = main.default_user_data_file
        original_base_file = main.default_ticket_base_file
        original_cover_file = main.default_ticket_cover_file
        original_event_get = pygame.event.get
        try:
            main.default_user_data_file = lambda: user_file
            main.default_ticket_base_file = lambda: base_file
            main.default_ticket_cover_file = lambda: cover_file
            main.register_account("rotate", "abc123", user_file)

            batches = [
                [pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": 1})],
                [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (120, 120)})],
                [pygame.event.Event(pygame.MOUSEMOTION, {"pos": (520, 260), "rel": (400, 140), "buttons": (1, 0, 0)})],
                [pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (520, 260)})],
                [pygame.event.Event(pygame.QUIT)],
            ]

            def fake_event_get():
                return batches.pop(0) if batches else []

            pygame.event.get = fake_event_get
            main.main_game("rotate", face_value=10)

            user = json.loads(user_file.read_text(encoding="utf-8"))[0]
            self.assertEqual(user["balance"], 190)
        finally:
            pygame.event.get = original_event_get
            main.default_user_data_file = original_user_data_file
            main.default_ticket_base_file = original_base_file
            main.default_ticket_cover_file = original_cover_file
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
