import tempfile
import unittest
from pathlib import Path

from utils.single_instance import SingleInstanceLock


class SingleInstanceLockTests(unittest.TestCase):
    def test_second_lock_cannot_be_acquired_until_first_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roselinne.lock"
            first = SingleInstanceLock(path)
            second = SingleInstanceLock(path)
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
            finally:
                second.release()
                first.release()

            self.assertTrue(second.acquire())
            second.release()


if __name__ == "__main__":
    unittest.main()
