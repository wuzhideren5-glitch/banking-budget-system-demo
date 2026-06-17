from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.knowledge_base import KnowledgeBaseService
from app.services.agent_domain_lexicon import AgentDomainLexicon, normalize_for_match


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class AgentDomainLexiconTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.kb_root = root / "kb"
        self.common_db = root / "common.db"
        self.budget_db = root / "budget_2026.db"

        _write(
            self.kb_root / "01_data_semantics" / "data_dictionary_seed.csv",
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
            self.kb_root / "01_data_semantics" / "field_table_name_mapping_zh.json",
            '{"table_name_mapping":{"budget_summary":"预算汇总"},"field_name_mapping":{"metric_level1":"指标一级"}}',
        )
        _write(
            self.kb_root / "04_term_synonyms" / "synonyms_seed.csv",
            "\n".join(
                [
                    "domain,term,normalized_type,normalized_code,normalized_name,confidence,requires_confirmation,notes",
                    "org_product,汽金,org_product,A03,汽车金融,0.92,true,current",
                    "data_account,汽金贷款利息收入,data_account,A03.03.01.01.01.078,汽金贷款利息收入,1.00,false,current",
                    "data_account,开心贷款利息收入,data_account,N1003,开心贷款利息收入,1.00,false,retired_old_code",
                    "org_product,个人住房贷款,org_product,Z0001,个人住房贷款,1.00,false,retired_old_product",
                ]
            ),
        )

        with sqlite3.connect(self.common_db) as conn:
            conn.executescript(
                """
                CREATE TABLE dept_account(dept_code TEXT, dept_name TEXT);
                CREATE TABLE org_product_tree_snapshot(
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE data_account(data_acct_code TEXT, data_acct_name TEXT);
                CREATE TABLE data_account_metric_node(node_code TEXT, node_name TEXT, is_active INTEGER);
                CREATE TABLE org_product_metric_table(
                    entity_code TEXT,
                    table_name TEXT,
                    payload_json TEXT
                );

                INSERT INTO dept_account VALUES ('Y103', '汽车金融部');
                INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A03","name":"汽车金融","children":[]}]}]}', 'now');
                INSERT INTO data_account VALUES ('A03.03.01.01.01.078', '汽金贷款利息收入');
                INSERT INTO data_account VALUES ('Z99.01.001', '孤立运行数据科目');
                INSERT INTO data_account_metric_node VALUES ('A03.03.02', '净利息收入', 1);
                INSERT INTO data_account_metric_node VALUES ('Z99.01', '孤立运行指标节点', 1);
                INSERT INTO org_product_metric_table VALUES (
                    'A03',
                    '业务状况表',
                    '{"metrics":[{"code":"A0303010101078","name":"汽金管理贷款余额"},{"code":"A0305","name":"汽金05指标","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER"}]}'
                );
                """
            )

        with sqlite3.connect(self.budget_db) as conn:
            conn.executescript(
                """
                CREATE TABLE budget_summary(
                    metric_level1 TEXT,
                    metric_level2 TEXT,
                    metric_level3 TEXT,
                    dept_level1 TEXT,
                    dept_level2 TEXT,
                    dept_level3 TEXT,
                    data_code_name TEXT,
                    product_code_name TEXT
                );

                INSERT INTO budget_summary VALUES (
                    '净利息收入',
                    '贷款利息收入',
                    '汽金贷款利息收入',
                    '公司总部',
                    '零售信贷',
                    '汽车金融部',
                    'A03.03.01.01.01.078 汽金贷款利息收入',
                    'A03 汽车金融'
                );
                """
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _load(self) -> AgentDomainLexicon:
        return AgentDomainLexicon.load(
            kb_service=KnowledgeBaseService(self.kb_root),
            common_db=self.common_db,
            budget_db=self.budget_db,
        )

    def test_current_terms_feed_agent_domain_and_semantic_retrieval(self) -> None:
        lexicon = self._load()

        self.assertIn(normalize_for_match("汽金贷款利息收入"), lexicon.strong_terms)
        self.assertIn(normalize_for_match("汽车金融部"), lexicon.strong_terms)
        self.assertIn(normalize_for_match("汽金管理贷款余额"), lexicon.strong_terms)
        self.assertIn(normalize_for_match("A03业务状况表A0303010101078"), lexicon.strong_terms)
        self.assertIn(normalize_for_match("汽金05指标"), lexicon.strong_terms)
        self.assertNotIn(normalize_for_match("孤立运行数据科目"), lexicon.strong_terms)
        self.assertNotIn(normalize_for_match("孤立运行指标节点"), lexicon.strong_terms)

        hits = lexicon.domain_hit_profile("请查询汽金贷款利息收入预算执行")
        self.assertGreaterEqual(hits["strong_hits"], 1)

        semantic = lexicon.semantic_budget_retrieve("汽金贷款利息收入趋势")
        self.assertGreaterEqual(float(semantic["score"]), 0.9)

    def test_dictionary_missing_terms_do_not_enter_agent_lexicon(self) -> None:
        lexicon = self._load()

        combined_terms = set(lexicon.strong_terms)
        combined_terms.update(lexicon.weak_terms)
        combined_terms.update(str(item["term"]) for item in lexicon.semantic_budget_corpus)

        payload = "\n".join(sorted(combined_terms))
        self.assertNotIn("n1003", payload)
        self.assertNotIn("z0001", payload)
        self.assertNotIn("开心贷款利息收入", payload)


if __name__ == "__main__":
    unittest.main()
