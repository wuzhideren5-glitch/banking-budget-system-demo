from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.knowledge_base import KnowledgeBaseService


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class KnowledgeBaseServiceTests(unittest.TestCase):
    def _service(self) -> KnowledgeBaseService:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        _write(
            root / "01_data_semantics" / "data_dictionary_seed.csv",
            "\n".join(
                [
                    "entity_type,entity_code,entity_name,source_table,parent_code,level,value_type,description,status,last_verified_at",
                    "dept_account,Y103,汽车金融部,dept_account,Y1,2,,部门科目,active,2026-06-01T00:00:00+08:00",
                    "org_product,A03,汽车金融,org_product_tree_snapshot,A,3,,机构及产品,active,2026-06-01T00:00:00+08:00",
                    "metric_node,A03.03.02,净利息收入,data_account_metric_node,A03.03,3,,product=A03,active,2026-06-01T00:00:00+08:00",
                    "data_account,A03.03.01.01.01.078,汽金贷款利息收入,data_account,A03.03.01,5,金额,scope=PRODUCT:A03,active,2026-06-01T00:00:00+08:00",
                ]
            ),
        )
        _write(
            root / "04_term_synonyms" / "synonyms_seed.csv",
            "\n".join(
                [
                    "domain,term,normalized_type,normalized_code,normalized_name,confidence,requires_confirmation,notes",
                    "org_product,汽金,org_product,A03,汽车金融,0.92,true,current",
                    "data_account,汽金贷款利息收入,data_account,A03.03.01.01.01.078,汽金贷款利息收入,1.00,false,current",
                    "data_account,开心贷款利息收入,data_account,N1003,开心贷款利息收入,1.00,false,retired_old_code",
                    "org_product,个人住房贷款,org_product,Z0001,个人住房贷款,1.00,false,retired_old_product",
                    "budget_keyword,预算,builtin_budget_term,kw_budget,预算,0.98,false,current_keyword",
                ]
            ),
        )
        _write(root / "02_metric_definitions" / "metric_catalog_seed.yaml", 'metrics: []\n')
        return KnowledgeBaseService(root)

    def tearDown(self) -> None:
        tmp = getattr(self, "tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_current_synonym_rows_drop_codes_missing_from_current_dictionary(self) -> None:
        service = self._service()

        rows = service.read_current_synonym_rows()
        payload = json.dumps(rows, ensure_ascii=False)

        self.assertIn("A03.03.01.01.01.078", payload)
        self.assertIn("kw_budget", payload)
        self.assertNotIn("N1003", payload)
        self.assertNotIn("Z0001", payload)

    def test_current_synonym_rows_reject_retired_report_axis_seed(self) -> None:
        service = self._service()
        _write(
            service.paths.synonyms_seed,
            "\n".join(
                [
                    "domain,term,normalized_type,normalized_code,normalized_name,confidence,requires_confirmation,notes",
                    "report_account,报告科目利润,report_account,X0301,报告科目利润,1.00,false,retired_report_axis",
                ]
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "已退休业务口径"):
            service.read_current_synonym_rows()

    def test_current_synonym_rows_reject_plural_report_accounts_alias(self) -> None:
        service = self._service()
        _write(
            service.paths.synonyms_seed,
            "\n".join(
                [
                    "domain,term,normalized_type,normalized_code,normalized_name,confidence,requires_confirmation,notes",
                    "report_accounts,旧报表科目别名,report_accounts,X0301,旧报表科目别名,1.00,false,legacy_plural_alias",
                ]
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "report_accounts"):
            service.read_current_synonym_rows()

    def test_current_synonym_rows_reject_retired_driver_axis_seed(self) -> None:
        service = self._service()
        _write(
            service.paths.synonyms_seed,
            "\n".join(
                [
                    "domain,term,normalized_type,normalized_code,normalized_name,confidence,requires_confirmation,notes",
                    "driver_indicator,旧驱动指标,driver_indicator,DR01,旧驱动指标,1.00,false,driver_source_priority",
                ]
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "driver_indicator"):
            service.read_current_synonym_rows()

    def test_search_context_rejects_retired_report_axis_memory(self) -> None:
        service = self._service()
        _write(
            service.paths.conversation_seed,
            json.dumps(
                {
                    "user_question": "旧报告科目利润",
                    "analysis_summary": "report_account path",
                    "embedding_text": "legacy_report_code",
                },
                ensure_ascii=False,
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "已退休业务口径"):
            service.search_context("利润")

    def test_search_context_rejects_retired_bi_and_fact_memory(self) -> None:
        service = self._service()
        _write(
            service.paths.conversation_seed,
            json.dumps(
                {
                    "user_question": "旧管控口径费用执行",
                    "analysis_summary": "control_item_subject_mapping maps old BI subjects",
                    "embedding_text": "budget_data.needs_calc legacy fact flag",
                },
                ensure_ascii=False,
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "control_item_subject_mapping"):
            service.search_context("费用")

    def test_search_context_uses_only_current_synonym_codes(self) -> None:
        service = self._service()

        current = service.search_context("汽金贷款利息收入", top_k=5)
        current_payload = json.dumps(current["matches"]["synonyms"], ensure_ascii=False)
        retired = service.search_context("开心贷款利息收入", top_k=5)
        retired_payload = json.dumps(retired["matches"]["synonyms"], ensure_ascii=False)

        self.assertIn("A03.03.01.01.01.078", current_payload)
        self.assertNotIn("N1003", retired_payload)


if __name__ == "__main__":
    unittest.main()
