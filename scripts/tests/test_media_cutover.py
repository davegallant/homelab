import importlib.util
import pathlib
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "media-cutover.py"
SPEC = importlib.util.spec_from_file_location("media_cutover", SCRIPT)
media_cutover = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media_cutover)


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tempdir.name)
        self.source = self.root / "movie.mp4"
        self.candidate = self.root / "movie.hevc.mp4"
        self.backup = self.root / "movie.mp4.original"
        self.report = self.root / "validation.json"
        self.source.write_bytes(b"original-media")
        self.candidate.write_bytes(b"smaller-hevc-media")
        self.write_report()

    def tearDown(self):
        self.tempdir.cleanup()

    def write_report(self):
        media_cutover.write_validation_report(
            self.report,
            {
                "passed": True,
                "source": str(self.source.resolve()),
                "candidate": str(self.candidate.resolve()),
                "source_sha256": media_cutover.sha256(self.source),
                "candidate_sha256": media_cutover.sha256(self.candidate),
            },
        )

    def test_promote_keeps_original_as_backup(self):
        media_cutover.promote(self.source, self.candidate, self.report, self.backup)
        self.assertEqual(self.source.read_bytes(), b"smaller-hevc-media")
        self.assertEqual(self.backup.read_bytes(), b"original-media")
        self.assertTrue(self.candidate.exists(), "candidate is retained for rollback until cleanup")

    def test_promotion_refuses_source_changed_after_validation(self):
        self.source.write_bytes(b"changed-original")
        with self.assertRaisesRegex(media_cutover.PipelineError, "source changed"):
            media_cutover.promote(self.source, self.candidate, self.report, self.backup)
        self.assertEqual(self.source.read_bytes(), b"changed-original")
        self.assertFalse(self.backup.exists())

    def test_promotion_refuses_to_overwrite_existing_backup(self):
        self.backup.write_bytes(b"keep-existing-backup")
        with self.assertRaisesRegex(media_cutover.PipelineError, "backup already exists"):
            media_cutover.promote(self.source, self.candidate, self.report, self.backup)
        self.assertEqual(self.source.read_bytes(), b"original-media")
        self.assertEqual(self.backup.read_bytes(), b"keep-existing-backup")

    def test_promotion_refuses_hardlinked_source(self):
        hardlink = self.root / "movie-hardlink.mp4"
        hardlink.hardlink_to(self.source)
        with self.assertRaisesRegex(media_cutover.PipelineError, "hard-linked"):
            media_cutover.promote(self.source, self.candidate, self.report, self.backup)
        self.assertEqual(self.source.read_bytes(), b"original-media")
        self.assertFalse(self.backup.exists())


if __name__ == "__main__":
    unittest.main()
