import importlib.util
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)
from shot_parser import parse_script  # noqa: E402

GOOD1 = "### SHOT 1\nCONTINUOUS: NO\nPROMPT: A woman walks along the stone steps at sunrise.\n"


def real_script():
    with open(os.path.join(PKG, "example_workflows", "sample_scripts.txt"), "rb") as f:
        return f.read().decode("utf-8")        # keeps the CRLF line endings of the real file


class ParserTests(unittest.TestCase):
    def test_clean_one_shot(self):
        r = parse_script(GOOD1)
        self.assertEqual((r.shot_count, r.total_seconds, r.chunk_seconds), (1, 15, 15))
        self.assertEqual(r.shots_text, "0-15: A woman walks along the stone steps at sunrise.")
        self.assertFalse(r.errors)

    def test_users_real_script_default_15s(self):
        r = parse_script(real_script())
        self.assertEqual(r.shot_count, 2)
        self.assertEqual(r.total_seconds, 30)
        lines = r.shots_text.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("0-15: [Push in, slow]"))
        self.assertTrue(lines[1].startswith("15-30: [Tilt down, macro]"))
        self.assertNotIn("\r", r.shots_text)                      # CRLF no longer leaks into the prompt
        self.assertEqual(len([w for w in r.warnings if "header says 8 s" in w]), 2)

    def test_users_real_script_8s_matches_headers(self):
        r = parse_script(real_script(), shot_seconds=8, max_shot_seconds=15)
        self.assertEqual((r.shot_count, r.total_seconds), (2, 16))
        self.assertTrue(r.shots_text.split("\n")[1].startswith("8-16:"))
        self.assertFalse(r.warnings)

    def test_one_shot_cut_from_real_script(self):
        one = real_script().split("### SHOT 2")[0]
        r = parse_script(one, shot_seconds=8)
        self.assertEqual((r.shot_count, r.total_seconds), (1, 8))
        self.assertFalse(r.errors)

    def test_format_guide_comment_is_not_a_shot(self):          # old workflow counted this as a 2nd shot
        script = "Write each shot as '### SHOT n' then CONTINUOUS then PROMPT.\n\n" + GOOD1
        r = parse_script(script)
        self.assertEqual((r.markers_found, r.shot_count, r.total_seconds), (1, 1, 15))

    def test_half_written_second_shot_is_an_error_not_a_phantom(self):
        r = parse_script(GOOD1 + "\n### SHOT 2\n(TODO)\n")
        self.assertTrue(any("Shot 2" in e and "PROMPT" in e for e in r.errors))

    def test_missing_continuous_line_is_fine(self):
        r = parse_script("### SHOT 1\nPROMPT: only a prompt\n")
        self.assertEqual(r.shot_count, 1)
        self.assertFalse(r.errors)

    def test_zero_padded_and_no_space_markers(self):
        r = parse_script("###SHOT 01\nPROMPT: a\n\n### SHOT 02: Title (0:00 - 0:05)\nPROMPT: b\n")
        self.assertEqual([s.shot_id for s in r.shots], [1, 2])
        self.assertEqual(r.shots[1].title, "Title")

    def test_gap_in_ids_has_no_gap_in_time(self):               # old workflow produced 0-15 and 30-45
        script = GOOD1 + "\n### SHOT 3\nCONTINUOUS: NO\nPROMPT: second part.\n"
        r = parse_script(script)
        self.assertEqual(r.shots_text.split("\n")[1], "15-30: second part.")
        self.assertTrue(any("gaps" in w for w in r.warnings))
        self.assertEqual(r.total_seconds, 30)

    def test_duplicate_ids_error(self):
        r = parse_script(GOOD1 + GOOD1)
        self.assertTrue(any("more than once" in e for e in r.errors))

    def test_first_shot_id_skips_earlier(self):
        r = parse_script(GOOD1 + "\n### SHOT 2\nPROMPT: two\n", first_shot_id=2)
        self.assertEqual(r.shots_text, "0-15: two")
        self.assertEqual(r.skipped_ids, [1])

    def test_multiline_prompt_collapsed_and_picture_alias(self):
        r = parse_script("### SHOT 1\nPROMPT: <Picture 1> walks\nto the <Picture 2> door.\n")
        self.assertEqual(r.shots_text, "0-15: @pic1 walks to the @pic2 door.")
        r2 = parse_script("### SHOT 1\nPROMPT: <Picture 1> walks\n", picture_alias=False)
        self.assertIn("<Picture 1>", r2.shots_text)

    def test_duration_over_cap_and_no_markers(self):
        self.assertTrue(parse_script(GOOD1, shot_seconds=20, max_shot_seconds=15).errors)
        r = parse_script("just some text, no markers")
        self.assertTrue(any("No shot markers" in e for e in r.errors))
        self.assertEqual(r.shot_count, 0)

    def test_max_shots(self):
        r = parse_script(GOOD1 + "\n### SHOT 2\nPROMPT: b\n", max_shots=1)
        self.assertTrue(any("max_shots" in e for e in r.errors))

    def test_fractional_header_and_empty_input(self):
        r = parse_script("### SHOT 1: x (0:00 - 1:05)\nPROMPT: a\n", shot_seconds=15)
        self.assertEqual(r.shots[0].header_seconds, 65)
        self.assertTrue(parse_script("").errors)


class NodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        fp = types.ModuleType("folder_paths")
        fp.get_input_directory = lambda: cls.tmp
        sys.modules["folder_paths"] = fp
        spec = importlib.util.spec_from_file_location("shot_script_pkg", os.path.join(PKG, "__init__.py"),
                                                      submodule_search_locations=[PKG])
        cls.pkg = importlib.util.module_from_spec(spec)
        sys.modules["shot_script_pkg"] = cls.pkg
        spec.loader.exec_module(cls.pkg)
        cls.Load = cls.pkg.NODE_CLASS_MAPPINGS["LoadScriptFile"]
        cls.Parse = cls.pkg.NODE_CLASS_MAPPINGS["ShotScriptParser"]

    def write(self, rel, data=b"### SHOT 1\r\nPROMPT: hi\r\n"):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_dropdown_lists_text_files_and_refreshes(self):
        self.write("a.txt"); self.write("sub/b.md"); self.write("pic.png", b"x"); self.write("a/b/c/d/deep.txt")
        files = self.Load.INPUT_TYPES()["required"]["file"][0]
        self.assertIn("a.txt", files); self.assertIn("sub/b.md", files)
        self.assertNotIn("pic.png", files); self.assertNotIn("a/b/c/d/deep.txt", files)
        self.write("added_later.txt")
        self.assertIn("added_later.txt", self.Load.INPUT_TYPES()["required"]["file"][0])
        self.assertNotIn("optional", self.Load.INPUT_TYPES())            # no path field, no free path input
        self.assertEqual(self.Load.RETURN_NAMES, ("text", "path"))

    def test_validate_accepts_file_not_in_stale_list_and_rejects_bad(self):
        self.write("late.txt")
        self.assertIs(self.Load.VALIDATE_INPUTS("late.txt"), True)
        self.assertIn("not found", self.Load.VALIDATE_INPUTS("nope.txt"))
        self.assertIn("Choose file", self.Load.VALIDATE_INPUTS(""))
        self.assertIn("Choose file", self.Load.VALIDATE_INPUTS(self.pkg.nodes.NO_FILES))
        self.assertIn("inside the input folder", self.Load.VALIDATE_INPUTS("../../etc/passwd"))
        self.write("x.json", b"{}")
        self.assertIn("accepted", self.Load.VALIDATE_INPUTS("x.json"))

    def test_load_normalizes_crlf_and_bom_and_returns_full_path(self):
        p = self.write("crlf.txt", b"\xef\xbb\xbfline1\r\nline2\r\n")
        text, path = self.Load().load("crlf.txt")
        self.assertEqual(text, "line1\nline2\n")
        self.assertEqual(path, os.path.realpath(p))

    def test_upload_saves_in_input_folder_and_never_overwrites_a_different_file(self):
        save = self.pkg.nodes.save_upload
        self.assertEqual(save("up.txt", b"one"), "up.txt")
        self.assertEqual(save("up.txt", b"one"), "up.txt")                # same bytes: reused
        self.assertEqual(save("up.txt", b"two"), "up (1).txt")            # different bytes: kept apart
        with open(os.path.join(self.tmp, "up.txt"), "rb") as f:
            self.assertEqual(f.read(), b"one")
        self.assertIn("up (1).txt", self.Load.INPUT_TYPES()["required"]["file"][0])   # an uploaded file is in the list
        self.assertIs(self.Load.VALIDATE_INPUTS("up (1).txt"), True)

    def test_upload_uses_base_name_and_rejects_bad_files(self):
        save = self.pkg.nodes.save_upload
        self.assertEqual(save("..\\..\\evil/notes.md", b"x"), "notes.md")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "notes.md")))
        for bad in ("a.png", "", ".txt", "noext"):
            with self.assertRaises(ValueError):
                save(bad, b"x")
        with self.assertRaises(ValueError):
            save("big.txt", b"x" * (self.pkg.nodes.MAX_BYTES + 1))

    def test_web_directory_is_js_and_script_exists(self):
        self.assertEqual(self.pkg.WEB_DIRECTORY, "./js")
        self.assertTrue(os.path.isfile(os.path.join(PKG, "js", "load_script_file.js")))

    def test_gbk_fallback_and_is_changed(self):
        self.write("cn.txt", "### SHOT 1\nPROMPT: 清晨的光".encode("gb18030"))
        self.assertIn("清晨", self.Load().load("cn.txt")[0])
        a = self.Load.IS_CHANGED("cn.txt")
        self.write("cn.txt", b"### SHOT 1\nPROMPT: changed")
        self.assertNotEqual(a, self.Load.IS_CHANGED("cn.txt"))
        self.assertEqual(self.Load.IS_CHANGED("missing.txt"), "missing")

    def test_parser_node_outputs_and_strict_fail_fast(self):
        node = self.Parse()
        shots, n, project, chunk, report = node.parse(real_script(), 1, 8, 15)
        self.assertEqual((n, project, chunk), (2, 16.0, 8.0))
        self.assertIsInstance(project, float)
        self.assertEqual(len(shots.split("\n")), 2)
        with self.assertRaises(ValueError) as ctx:
            node.parse("### SHOT 1\nPROMPT: a\n### SHOT 2\n(TODO)\n", 1, 15, 15)
        self.assertIn("nothing was rendered", str(ctx.exception))
        shots, n, *_ = node.parse("### SHOT 1\nPROMPT: a\n### SHOT 2\n(TODO)\n", 1, 15, 15, strict=False)
        self.assertEqual(n, 1)                                  # non-strict keeps what parsed

    def test_node_declarations_match_methods(self):
        for cls in (self.Load, self.Parse):
            self.assertTrue(hasattr(cls, cls.FUNCTION))
            self.assertEqual(len(cls.RETURN_TYPES), len(cls.RETURN_NAMES))
        self.assertEqual(self.Parse.RETURN_TYPES, ("STRING", "INT", "FLOAT", "FLOAT", "STRING"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
