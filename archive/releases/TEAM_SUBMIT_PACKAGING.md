---
name: team-submit-packaging-md
description: 组员提交源码包的打包说明和 AI skill，可直接发给同事或复制给 Codex/其他 AI 使用；用于合并审核，不用于 CTO 部署交付包。
---

# Team Submit 打包 Skill（组员版）

本文档可以直接发给组员，或复制给 Codex/其他 AI 作为打包 skill 使用。

它只适用于“组员提交给主线合并审核”的源码包，不适用于测试服务器部署包。部署包需要 `.env`、数据库、`var/data`、前端 `dist` 等运行资产时，请走 CTO 发布打包流程。

当前项目测试服务器口径是后端 `8009`、前端 `8443`。组员提交源码包时可以在说明里写清端口影响，但不要因为端口说明就把 `.env`、数据库、`dist` 或运行环境一起打进去。

## 一句话目标

把“本次功能相关的源码、文档、模板、说明”打成一个干净 zip，方便负责人/Codex 合并；不要把本机运行环境、历史包、无关 Excel、数据库快照一起打进去。

## 给组员的执行口令

可以把下面这段直接发给打包的人：

```text
请按 TEAM_SUBMIT_PACKAGING.md 的规则打一个 TeamSubmit 包：
1. 包名使用 TeamSubmit_YYYYMMDD_姓名_功能英文或拼音.zip。
2. 必须包含 apps、docs、根目录必要配置、交付说明。
3. 只按需包含本次功能依赖的模板、知识库、业务输入 Excel。
4. 禁止包含 node_modules、.venv、.env、var/data、data、dist、archive、releases、历史 zip、其他组员原始包。
5. 交付说明必须写清楚本次新增内容、修改范围、数据库影响、验证情况。
```

## 给 Codex/其他 AI 的 Skill 口令

如果组员也使用 Codex、Cursor、Claude Code 或其他 AI，可以直接复制下面这段：

```text
你是本项目的 Team Submit 打包助手。请只打包本次功能合并审核需要的源码、文档、模板和交付说明，不要打部署包。

请按以下规则执行：
1. 先识别当前项目根目录，不要在历史包、回退包、archive、release、TeamSubmit_* 原始包里面重复套娃打包。
2. 生成英文/ASCII 包名：TeamSubmit_YYYYMMDD_name_feature.zip。
3. 必须包含 apps、docs、根目录必要配置、start.sh、stop.sh、SUBMISSION_NOTE.md。
4. 按需包含 resources/download_template、resources/knowledge_base、resources/business_inputs 中本次功能直接依赖的具体文件。
5. 如涉及 .scratch/<feature-slug>/ 的 issue/PRD/设计记录，只包含本次功能对应的那个 .scratch 子目录。
6. 禁止包含 node_modules、.venv、.env、var/data、data、dist、archive、releases、历史 zip、其他组员包、日志、缓存、数据库快照。
7. 如涉及新增表、新增字段、主键、唯一约束、钩稽关系、初始化数据，必须输出数据库影响说明或 Excel，不能直接把本地数据库打进包。
8. 打包后执行 zip -T，并检查压缩包内没有禁止目录。
```

## 适用场景

- 组员完成一个功能模块，需要提交给项目主线合并。
- 组员修改了前端、后端、接口、初始化脚本、模板或文档，需要让别人能审查和合并。
- 组员需要明确说明“本次新增内容”和影响范围。
- 组员的本地文件夹命名不规整，也要按内容判断该带什么、该排除什么。

## 推荐包名

请使用英文/ASCII 文件名，避免跨机器、微信、服务器解压乱码。

推荐格式：

```text
TeamSubmit_YYYYMMDD_name_feature.zip
```

示例：

```text
TeamSubmit_20260601_panpan_expense_budget.zip
TeamSubmit_20260601_nick_simulation_v3.zip
TeamSubmit_20260601_kevin_metric_tree_fix.zip
```

## 必须包含

按当前仓库结构，默认应包含：

- `apps/`：主程序源码，包含 `apps/web` 前端和 `apps/api` 后端。
- `docs/`：PDD、PRD、接口规范、数据库规范、设计规范、验收说明等。
- `README.md`、`AGENTS.md`、`CONTEXT.md`、`CHANGELOG.md`。
- `package.json`、`package-lock.json`、`skills-lock.json`。
- `start.sh`、`stop.sh`。
- `docs/development/test-server-deployment.md`，或本地确实存在的 `测试服务器部署说明.md`。
- 本次功能相关的新增/修改模板、初始化脚本、接口说明、页面说明。
- 如果本次功能有本地 issue/PRD/设计记录，包含对应的 `.scratch/<feature-slug>/`，不要包含整个 `.scratch/`。
- 一份提交说明 Markdown，建议命名为 `SUBMISSION_NOTE.md`。

如果某个文件在组员本地不存在，不要临时伪造；在提交说明里写“本地无该文件”即可。

## 按需包含

以下内容只有本次功能确实依赖时才放进去，不要默认全量包含：

- `resources/download_template/`：本次修改导入/导出模板时包含。
- `resources/knowledge_base/`：本次修改 Agent、语义、提示词、指标定义、知识库配置时包含。
- `resources/business_inputs/`：只放本次功能直接依赖的 Excel/PPT/CSV，不要整目录乱塞。
- 根目录或子目录里的 `*.xlsx`、`*.xls`、`*.csv`：只放本次功能要用的那几张表。
- 数据库迁移脚本、初始化脚本、SQL、字段确认表：涉及表结构、主键、唯一约束、钩稽关系时必须包含。

## 禁止包含

组员提交包默认禁止包含：

- `.git/`
- `node_modules/`
- `.venv/`、`.venv312/`、`backend/.venv/`、`apps/api/.venv/` 等任何虚拟环境。
- `.env`、`.env.local`、密钥、账号、Token 等敏感配置。
- `var/data/`、`data/`、SQLite 数据库快照。
- `apps/web/dist/`，除非负责人明确要求提交部署产物。
- `archive/`、`releases/`、历史 zip、回退包、其他组员原始包。
- 根目录下已有的 `TeamSubmit_*`、`*_完整回退包_*`、`*_release_*` 等历史提交/回退/发布目录。
- `var/logs/`、`var/pids/`、备份目录、缓存目录、生成输出目录。
- `__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.vite/`。
- `.DS_Store`、`*.pyc`、`*.log`、`*.pid`、WPS 临时锁文件，如 `.~*`、`~$*`。

## 不规整文件夹的甄别规则

不要只看文件夹名字，因为组员交付包可能叫 `最终版`、`0519`、`新建文件夹`、`panpan打包`。

判断一个目录是否应该排除时，优先看内容：

- 看到 `node_modules`、`.venv`、`dist`、`var/data`、`data/*.db`，这是运行环境或产物，默认排除。
- 看到 `release`、`releases`、`archive`、`backup`、`回退包`、`历史包`，这是历史交付或备份，默认排除。
- 看到 `TeamSubmit_*`、`最终版`、`完整回退包`、`Codex0508`、`0511` 这类已交付目录时，先判断它是不是本次当前工作目录；如果只是旧包或别人原始包，不要再次套娃打包。
- 看到另一个完整 `package.json`、`apps/`、`docs/`、交付说明同时存在，可能是别人原始包，不要再次套娃打包。
- 看到 Excel/PPT/图片很多时，只保留本次功能明确引用的文件，并在提交说明中列出用途。
- 看到 `.env`、账号、Token、数据库文件时，直接排除；如果确实需要部署资产，改走 CTO 发布打包流程。

## 数据库变更规则

组员不能把本地数据库快照当作数据库变更交付。

如果涉及以下任一事项，必须单独写数据库影响说明，等待负责人确认后再合并：

- 新增数据库表。
- 新增字段。
- 修改主键。
- 修改唯一约束。
- 修改钩稽关系、汇总逻辑、映射关系。
- 修改初始化数据、默认规则、机构树、科目树、指标库。

数据库影响说明至少包含：

- 表名。
- 字段名、类型、是否必填、默认值。
- 主键/唯一约束变化。
- 初始化数据来源。
- 与现有 PDD/PRD/数据规范是否一致。
- 回滚方式。

建议直接复制下面这个模板；如果影响较多，可以另附 Excel：

```markdown
## 数据库影响说明

| 类型 | 表名 | 字段/主键/关系 | 当前状态 | 目标变更 | 初始化数据来源 | 是否需负责人确认 | 回滚方式 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 新增字段 | 示例表 | example_code TEXT NOT NULL DEFAULT '' | 无该字段 | 新增字段用于页面查询 | 无/某 Excel | 是 | 删除字段或回滚迁移 |

## 关键确认

- 是否新增表：
- 是否修改主键：
- 是否修改唯一约束：
- 是否修改钩稽/汇总/映射关系：
- 是否需要导入机构树/科目树/指标库/默认规则：
- 是否影响现有历史数据：
```

## 提交说明模板

请在提交包根目录放一份 Markdown，例如：

```text
SUBMISSION_NOTE.md
```

内容模板：

```markdown
# 本次提交说明

## 本次新增内容

- 新增/修改了什么功能：
- 解决了什么问题：
- 入口页面/菜单位置：

## 修改范围

- 前端：
- 后端：
- 接口：
- 数据库/初始化：
- 模板/Excel：
- 文档：

## 数据库影响

- 是否新增表：
- 是否新增字段：
- 是否修改主键/唯一约束：
- 是否修改钩稽关系：
- 是否需要初始化数据：
- 如有数据库影响，已附数据库影响说明/Excel：

## 依赖与启动

- 是否新增 npm 依赖：
- 是否新增 Python 依赖：
- 是否修改启动端口或环境变量：

## 验证情况

- `npm run build`：
- `python3 -m compileall -q apps/api/app`：
- 页面验证截图/说明：
- 接口验证说明：

## 已知风险

- 风险 1：
- 风险 2：
```

## 自动打包命令

如果在项目负责人机器上使用已有 `team-submit` 打包脚本，优先执行：

```bash
python /Users/penghui/.codex/skills/team-submit/scripts/package_team_submit.py \
  --project-root "$PWD" \
  --name "TeamSubmit_YYYYMMDD_name_feature" \
  --summary "本次新增内容：请填写本次功能说明"
```

如本次涉及下载模板：

```bash
python /Users/penghui/.codex/skills/team-submit/scripts/package_team_submit.py \
  --project-root "$PWD" \
  --name "TeamSubmit_YYYYMMDD_name_feature" \
  --summary "本次新增内容：请填写本次功能说明" \
  --include-download-template
```

如本次涉及知识库：

```bash
python /Users/penghui/.codex/skills/team-submit/scripts/package_team_submit.py \
  --project-root "$PWD" \
  --name "TeamSubmit_YYYYMMDD_name_feature" \
  --summary "本次新增内容：请填写本次功能说明" \
  --include-knowledge-base
```

如本次确实依赖某个业务 Excel，请用 `--extra` 精准指定，不要整包包含全部业务输入：

```bash
python /Users/penghui/.codex/skills/team-submit/scripts/package_team_submit.py \
  --project-root "$PWD" \
  --name "TeamSubmit_YYYYMMDD_name_feature" \
  --summary "本次新增内容：请填写本次功能说明" \
  --extra "resources/business_inputs/文件名.xlsx"
```

## 手工打包命令

在项目根目录执行，默认只打源码、文档、配置和提交说明。这个写法只会加入真实存在的文件，避免因为某个可选说明文件不存在导致 `zip` 失败：

```bash
PACKAGE_NAME="TeamSubmit_YYYYMMDD_name_feature"

INCLUDE_PATHS=()
for path in \
  apps docs src backend "Design docs" \
  README.md AGENTS.md CONTEXT.md CHANGELOG.md \
  package.json package-lock.json skills-lock.json \
  start.sh stop.sh \
  docs/development/test-server-deployment.md \
  测试服务器部署说明.md \
  TEAM_SUBMIT_PACKAGING.md SUBMISSION_NOTE.md
do
  [ -e "$path" ] && INCLUDE_PATHS+=("$path")
done

zip -r "${PACKAGE_NAME}.zip" "${INCLUDE_PATHS[@]}" \
  -x "*/node_modules/*" "*/.venv/*" "*/.venv312/*" "*/.git/*" \
     "*/var/data/*" "*/data/*" "*/dist/*" "*/archive/*" "*/releases/*" "*/TeamSubmit_*/*" \
     "*/var/logs/*" "*/var/pids/*" "*/outputs/*" "*/__pycache__/*" "*/.pytest_cache/*" \
     "*/.mypy_cache/*" "*/.ruff_cache/*" "*/.vite/*" \
     "*.pyc" "*.log" "*.pid" ".DS_Store" "*/.~*" "*/~$*"
```

如果要额外带模板或指定 Excel，把对应路径追加到 `INCLUDE_PATHS`，例如：

```bash
INCLUDE_PATHS+=(resources/download_template resources/business_inputs/文件名.xlsx)
```

## 提交前自查

提交前至少检查：

- 包名是英文/ASCII，能跨机器正常解压。
- 包内有 `SUBMISSION_NOTE.md` 或等价交付说明。
- 包内没有 `.env`、数据库、`node_modules`、虚拟环境、历史包。
- 前后端配套文件都带齐，不要只提交页面却漏后端接口。
- 本次依赖的模板、Excel、初始化说明已精准包含，不含无关大文件。
- 涉及数据库结构变化时，已单独说明并等待确认。
- 能运行的情况下，已执行 `npm run build`。
- 能运行的情况下，已执行 `python3 -m compileall -q apps/api/app`。
- 已执行 `zip -T TeamSubmit_YYYYMMDD_name_feature.zip` 验证压缩包完整。

## 验包命令

压缩包生成后，建议执行：

```bash
zip -T TeamSubmit_YYYYMMDD_name_feature.zip
unzip -l TeamSubmit_YYYYMMDD_name_feature.zip | grep -E "node_modules|\\.venv|\\.env|var/data|/data/|dist|archive|releases|TeamSubmit_|\\.db|\\.sqlite" || true
```

如果第二条命令打印出命中项，需要人工确认是否误包含禁止内容。

## 常见错误

- 只复制单个页面，漏掉后端接口、API 类型、路由注册。
- 只复制后端，漏掉前端入口、菜单、页面组件。
- 把 `node_modules`、`.venv`、`dist` 一起打进去，导致包巨大且跨系统不可用。
- 把 `.env` 或数据库发出来，造成敏感信息泄露和数据污染。
- 把 `archive/`、`releases/`、其他组员原始包再次套娃打包。
- 改了数据库字段但没有说明主键、唯一约束、初始化数据和兼容影响。
- 改了导入模板但没有附对应模板或字段说明。
- 把无关 Excel 全量打包，导致负责人无法甄别哪些是功能依赖。

## 交付给负责人的内容

最终只需要交付：

- `TeamSubmit_YYYYMMDD_name_feature.zip`
- 简短说明：本次新增内容、是否涉及数据库、是否需要负责人确认主键/字段/初始化数据。

## 负责人/Codex 合并接收位置

负责人收到 zip 后，建议放到项目内：

```text
archive/team_packages/incoming/YYYYMMDD/<package-name>/
```

然后只做差异合并，不要整包覆盖当前项目。
