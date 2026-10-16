import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ai.memory import MemoryManager


class MemoryManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_message_id_prevents_duplicate_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MemoryManager(SimpleNamespace(
                db_path=Path(directory) / "memory.db",
                memory_max_messages=20,
            ))
            await manager.add_message(42, 7, "user", "sayang", 123)
            await manager.add_message(42, 7, "user", "sayang", 123)
            await manager.add_message(42, 7, "assistant", "Baik.", 123)
            await manager.add_message(42, 7, "assistant", "Baik.", 123)

            history = await manager.get_history(42, 7)

        self.assertEqual(history, [
            {"role": "user", "content": "sayang"},
            {"role": "assistant", "content": "Baik."},
        ])

    async def test_different_message_ids_with_same_text_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MemoryManager(SimpleNamespace(
                db_path=Path(directory) / "memory.db",
                memory_max_messages=20,
            ))
            await manager.add_message(42, 7, "user", "halo", 123)
            await manager.add_message(42, 7, "assistant", "Hm.", 123)
            await manager.add_message(42, 7, "user", "halo", 124)
            await manager.add_message(42, 7, "assistant", "Hm.", 124)

            history = await manager.get_history(42, 7)

        self.assertEqual(len(history), 4)


if __name__ == "__main__":
    unittest.main()
