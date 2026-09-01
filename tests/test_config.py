import os
import tempfile
import unittest
from pathlib import Path

from pricewatch import config


class TestParseEnvFile(unittest.TestCase):
    def write(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / ".env"
        p.write_text(text, encoding="utf-8")
        return p

    def test_absent_file_is_empty_not_an_error(self):
        self.assertEqual(config.parse_env_file(Path("/nope/.env")), {})

    def test_parses_comments_blanks_quotes_and_export(self):
        p = self.write('# c\n\nA=1\nB="two"\nC=\'three\'\nexport D=4\nnoequals\n')
        self.assertEqual(config.parse_env_file(p),
                         {"A": "1", "B": "two", "C": "three", "D": "4"})

    def test_value_containing_equals_survives(self):
        p = self.write("TOK=abc=def==\n")
        self.assertEqual(config.parse_env_file(p)["TOK"], "abc=def==")

    def test_only_one_quote_pair_is_stripped(self):
        p = self.write("""A="'x'"\n""")
        self.assertEqual(config.parse_env_file(p)["A"], "'x'")


class TestPrecedence(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.p = Path(d.name) / ".env"
        self.p.write_text("K=from_file\n", encoding="utf-8")
        os.environ.pop("K", None)
        self.addCleanup(lambda: os.environ.pop("K", None))

    def test_env_file_used_when_environment_is_unset(self):
        self.assertEqual(config.get("K", env_path=self.p), "from_file")

    def test_real_environment_wins(self):
        os.environ["K"] = "from_env"
        self.assertEqual(config.get("K", env_path=self.p), "from_env")

    def test_empty_environment_value_falls_through_to_the_file(self):
        os.environ["K"] = ""
        self.assertEqual(config.get("K", env_path=self.p), "from_file")

    def test_require_raises_with_guidance(self):
        with self.assertRaises(KeyError) as cm:
            config.require("MISSING", "Do the thing.", env_path=self.p)
        self.assertIn("Do the thing.", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
