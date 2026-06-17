import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db_bootstrap.generated_paths import validate_generated_file_paths
from scripts.prepare_deploy_generated_paths import prepare_generated_paths


class PrepareDeployGeneratedPathsTest(unittest.TestCase):
    def test_rewrites_templates_and_clears_unshipped_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "var" / "data"
            template_dir = data_dir / "smart_report_templates"
            template_dir.mkdir(parents=True)
            (template_dir / "report_v1.docx").write_bytes(b"template")

            conn = sqlite3.connect(data_dir / "common.db")
            try:
                conn.executescript(
                    """
                    CREATE TABLE smart_report_template (
                      template_id INTEGER PRIMARY KEY,
                      file_path TEXT NOT NULL,
                      status TEXT NOT NULL DEFAULT 'active'
                    );
                    CREATE TABLE smart_report_instance (
                      instance_id INTEGER PRIMARY KEY,
                      output_file_path TEXT
                    );
                    CREATE TABLE smart_ppt_instance (
                      instance_id INTEGER PRIMARY KEY,
                      output_file_path TEXT
                    );
                    INSERT INTO smart_report_template VALUES
                      (1, '/Users/penghui/project/var/data/smart_report_templates/report_v1.docx', 'active');
                    INSERT INTO smart_report_instance VALUES
                      (1, '/Users/penghui/project/var/data/smart_report_outputs/old_report.docx');
                    INSERT INTO smart_ppt_instance VALUES
                      (1, '/Users/penghui/project/var/data/smart_report_outputs/old_ppt.pptx');
                    """
                )
                conn.commit()
            finally:
                conn.close()

            result = prepare_generated_paths(data_dir)

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["template_changed"], 1)
            self.assertEqual(result["output_cleared"], 2)

            conn = sqlite3.connect(data_dir / "common.db")
            try:
                template_path = conn.execute(
                    "SELECT file_path FROM smart_report_template WHERE template_id = 1"
                ).fetchone()[0]
                report_path = conn.execute(
                    "SELECT output_file_path FROM smart_report_instance WHERE instance_id = 1"
                ).fetchone()[0]
                ppt_path = conn.execute(
                    "SELECT output_file_path FROM smart_ppt_instance WHERE instance_id = 1"
                ).fetchone()[0]

                self.assertEqual(template_path, str((template_dir / "report_v1.docx").resolve()))
                self.assertIsNone(report_path)
                self.assertIsNone(ppt_path)
                validate_generated_file_paths(conn, data_dir)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
