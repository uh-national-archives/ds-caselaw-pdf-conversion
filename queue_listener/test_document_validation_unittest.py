"""Dependency-free negative and normal tests for DOCX input validation."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from document_validation import (
    DocumentRejected,
    checked_etag,
    checked_source_key,
    validate_docx_file,
)


class TestDocumentValidation(unittest.TestCase):
    def test_normal_s3_key(self):
        self.assertEqual(checked_source_key("caselaw%2F2026%2Fjudgment.docx"), "caselaw/2026/judgment.docx")

    def test_reject_non_docx_and_traversal(self):
        for key in ("../judgment.docx", "/case.docx", "case.pdf", "a//b.docx", "a\\b.docx"):
            with self.subTest(key=key), self.assertRaises(DocumentRejected):
                checked_source_key(key)

    def test_good_single_and_multipart_etag(self):
        self.assertEqual(checked_etag('"' + "a" * 32 + '"'), "a" * 32)
        self.assertEqual(checked_etag("a" * 32 + "-2"), "a" * 32 + "-2")

    def test_reject_unsafe_etag(self):
        for etag in ("../../test", "anything", "", "ab" * 16 + "/a", "a" * 32 + "-0"):
            with self.subTest(etag=etag), self.assertRaises(DocumentRejected):
                checked_etag(etag)

    def test_valid_word_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "valid.docx"
            with zipfile.ZipFile(file, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", "<document/>")
            validate_docx_file(file)

    def test_reject_fake_file_and_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "fake.docx"
            for payload in (b"", b"%PDF-1.4\nnot-a-docx", b"hello"):
                file.write_bytes(payload)
                with self.assertRaises(DocumentRejected):
                    validate_docx_file(file)

    def test_reject_archive_with_no_word_document(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "fake.docx"
            with zipfile.ZipFile(file, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
            with self.assertRaises(DocumentRejected):
                validate_docx_file(file)

    def test_reject_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "bad.docx"
            with zipfile.ZipFile(file, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", "<document/>")
                archive.writestr("../escape.txt", "bad")
            with self.assertRaises(DocumentRejected):
                validate_docx_file(file)

    def test_reject_excessive_uncompressed_size(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "large.docx"
            with zipfile.ZipFile(file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", "x" * (151 * 1024 * 1024))
            with self.assertRaises(DocumentRejected):
                validate_docx_file(file)


if __name__ == "__main__":
    unittest.main()
