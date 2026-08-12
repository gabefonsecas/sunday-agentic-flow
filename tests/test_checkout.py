import multiprocessing
from pathlib import Path
import subprocess
import tempfile
import unittest

from sunday.checkout import checkout_lease


def hold_checkout(repository: str, ready, release) -> None:
    with checkout_lease(Path(repository)):
        ready.set()
        release.wait(10)


class CheckoutLeaseTests(unittest.TestCase):
    def test_second_process_cannot_control_same_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            repository.mkdir()
            subprocess.run(
                ["git", "init", "-b", "main"], cwd=repository,
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            ready = multiprocessing.Event()
            release = multiprocessing.Event()
            process = multiprocessing.Process(
                target=hold_checkout, args=(str(repository), ready, release)
            )
            process.start()
            self.assertTrue(ready.wait(10))
            try:
                with self.assertRaisesRegex(RuntimeError, "Another Sunday run"):
                    with checkout_lease(repository):
                        pass
            finally:
                release.set()
                process.join(10)
            self.assertEqual(process.exitcode, 0)


if __name__ == "__main__":
    unittest.main()
