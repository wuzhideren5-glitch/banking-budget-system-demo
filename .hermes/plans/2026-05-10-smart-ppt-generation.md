# 智能生成 PPT 功能 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 在现有智能 Word 报告系统基础上，新增 PPTX 模板支持，实现智能 PPT 生成功能。

**Architecture:** 复用 `smart_report` 数据库表（模板/变量/实例/任务），新增 PPTX 占位符提取和渲染逻辑。后端新增 `smart_ppt_service.py` 处理 PPTX 特有渲染，前端 `AnalysisPPTContent.tsx` 接入真实 API。

**Tech Stack:** FastAPI (Python), python-pptx, React/TypeScript, aiosqlite, shadcn/ui

---

## 数据库改动

无需新建表！复用现有表，模板上传时设 `template_type='ppt'`。
已有表结构：`smart_report_template`(含 template_type)、`smart_report_template_variable`、`smart_report_instance`、`smart_report_job`。

---

### Task 1: 后端 — PPTX 占位符提取

**Objective:** 在 `SmartReportService` 中新增 `extract_placeholders_pptx()` 方法

**Files:**
- Modify: `backend/app/services/smart_report_service.py`

**Step 1: 新增方法**

在 `extract_placeholders` 方法后添加：

```python
def extract_placeholders_pptx(self, pptx_path: Path) -> list[str]:
    """从 PPTX 文件中提取所有 {{ variable }} 占位符"""
    from pptx import Presentation
    prs = Presentation(str(pptx_path))
    found: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text
                    for match in PLACEHOLDER_RE.finditer(text):
                        token = match.group(1).strip()
                        if token and token not in found:
                            found.append(token)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for match in PLACEHOLDER_RE.finditer(cell.text):
                            token = match.group(1).strip()
                            if token and token not in found:
                                found.append(token)
    return found
```

**Step 2: 修改模板上传入口**

在 `create_or_update_template()` 中，检测文件扩展名决定用哪个提取方法：
```python
if file.filename.lower().endswith('.pptx'):
    placeholders = self.extract_placeholders_pptx(target)
else:
    placeholders = self.extract_placeholders(target)
```

**Verification:** 上传一个带 `{{ param:year }}` 的 PPTX，确认变量被提取到 `smart_report_template_variable` 表。

---

### Task 2: 后端 — PPTX 渲染方法

**Objective:** 新增 `_render_pptx()` 方法，将 resolved values 填入 PPTX 模板

**Files:**
- Modify: `backend/app/services/smart_report_service.py`

**Step 1: 新增 `_render_pptx` 方法**

```python
def _render_pptx(self, template_path: Path, output_path: Path, resolved: dict[str, str]) -> None:
    """用 resolved values 替换 PPTX 模板中的占位符"""
    from pptx import Presentation
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="PPTX 模板文件不存在")
    
    prs = Presentation(str(template_path))
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    self._replace_pptx_paragraph(paragraph, resolved)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for paragraph in cell.text_frame.paragraphs:
                            self._replace_pptx_paragraph(paragraph, resolved)
    prs.save(str(output_path))


def _replace_pptx_paragraph(self, paragraph: Any, resolved: dict[str, str]) -> None:
    """替换 PPTX 段落中的 {{ }} 占位符，保留格式"""
    text = paragraph.text
    if "{{" not in text:
        return
    new_text = self._replace_text(text, resolved)
    if len(paragraph.runs) > 0:
        paragraph.runs[0].text = new_text
        for run in paragraph.runs[1:]:
            run.text = ""
```

**Verification:** 用 mock resolved dict 测试渲染一个简单 PPTX。

---

### Task 3: 后端 — 扩展 generate 端点支持 PPTX

**Objective:** 修改 `_render_instance` 方法，根据模板文件扩展名分支渲染

**Files:**
- Modify: `backend/app/services/smart_report_service.py`

**Step 1: 修改 `_render_instance`**

在 `_render_instance()` 的 Step 2 (渲染) 处改为分支：

```python
# 原代码:
# self._render_docx(template_path, output_path, resolved)

# 改为:
ext = template_path.suffix.lower()
if ext == '.pptx':
    self._render_pptx(template_path, output_path, resolved)
else:
    self._render_docx(template_path, output_path, resolved)
```

同时修改 `output_filename` 的后缀名：
```python
ext = template_path.suffix.lower()
output_filename = f"{prefix}_{instance_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
```

**Verification:** 通过 API 生成一个 PPT 报告实例，确认输出文件为 .pptx。

---

### Task 4: 后端 — 扩展模板上传支持 .pptx

**Objective:** 允许上传 .pptx 模板文件

**Files:**
- Modify: `backend/app/routers/smart_reports.py`

**Step 1: 修改 upload_template 端点**

```python
@router.post("/templates", response_model=SmartReportTemplateCreateResponse)
async def upload_template(
    file: UploadFile = File(...),
    template_code: str = Form(...),
    template_name: str = Form(...),
    template_type: str = Form("analysis"),
    remark: str | None = Form(None),
):
    # Validate file extension
    filename = (file.filename or "").lower()
    if not (filename.endswith(".docx") or filename.endswith(".pptx")):
        raise HTTPException(status_code=400, detail="请上传 .docx 或 .pptx 文件")
    ...
```

同时修改 service 中的校验：
```python
# create_or_update_template 中
if not file.filename or not (
    file.filename.lower().endswith(".docx") or file.filename.lower().endswith(".pptx")
):
    raise HTTPException(status_code=400, detail="请上传 .docx 或 .pptx 文件")
```

**Verification:** 上传 .pptx 文件成功，返回模板信息和提取到的占位符列表。

---

### Task 5: 后端 — Preview 方法支持 PPTX

**Objective:** `_render_preview_text` 支持 PPTX 格式

**Files:**
- Modify: `backend/app/services/smart_report_service.py`

**Step 1: 修改 `_render_preview_text`**

```python
def _render_preview_text(self, template_path: Path, resolved: dict[str, str]) -> str:
    ext = template_path.suffix.lower()
    if ext == '.pptx':
        from pptx import Presentation
        prs = Presentation(str(template_path))
        blocks: list[str] = []
        for i, slide in enumerate(prs.slides, 1):
            slide_texts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = self._replace_text(shape.text_frame.text, resolved).strip()
                    if text:
                        slide_texts.append(text)
            if slide_texts:
                blocks.append(f"--- Slide {i} ---")
                blocks.extend(slide_texts)
        return "\n".join(blocks)
    else:
        # existing docx logic
        ...
```

**Verification:** 调用 preview API 确认 PPTX 预览返回各 slide 内容。

---

### Task 6: 后端 — init_db 支持 template_type='ppt'

**Objective:** 确认/修改 template_type CHECK 约束

**Files:**
- Modify: `backend/app/init_db.py`

**Step 1: 检查 template_type CHECK 约束**

在 `smart_report_template` 建表语句中，如果 `template_type` 有 CHECK 约束限制值，需添加 `'ppt'`：

```sql
-- 原
template_type TEXT NOT NULL DEFAULT 'analysis' CHECK (template_type IN ('analysis', 'report', 'summary'))

-- 改为
template_type TEXT NOT NULL DEFAULT 'analysis' CHECK (template_type IN ('analysis', 'report', 'summary', 'ppt'))
```

**Verification:** 向 smart_report_template 表插入一条 `template_type='ppt'` 的记录确认不违反约束。

---

### Task 7: 前端 — AnalysisPPTContent 接入真实 API

**Objective:** 用真实 API 替换 mock 数据

**Files:**
- Modify: `src/app/components/AnalysisPPTContent.tsx`
- Modify: `src/lib/api.ts` (新增接口类型)

**Step 1: 添加 API 类型和函数到 `api.ts`**

```typescript
// 复用智能报告的 DTO
export interface SmartReportTemplateRow {
  template_id: number;
  template_code: string;
  template_name: string;
  template_type: string;
  status: string;
  version_no: number;
  remark?: string;
  created_at: string;
  updated_at: string;
  variable_count: number;
}

export interface SmartReportInstanceRow {
  instance_id: number;
  report_id?: number;
  template_id: number;
  template_name?: string;
  instance_name: string;
  generation_status: string;
  output_file_path?: string;
  error_message?: string;
  last_generated_at?: string;
  last_refresh_at?: string;
  created_at: string;
  updated_at: string;
}

export type SmartReportGenerateRequest = {
  template_id: number;
  report_id?: number;
  instance_name?: string;
  parameters: Record<string, unknown>;
  text_values?: Record<string, unknown>;
};

export type SmartReportGenerateResponse = {
  instance_id: number;
  job_id: number;
  output_filename: string;
  download_url: string;
  generated_at: string;
  resolved_values: Record<string, string>;
  warnings: string[];
};
```

**Step 2: 重写 `AnalysisPPTContent.tsx`**

```tsx
// 核心改动:
// 1. 用 useState + useEffect 从 API 获取 PPT 模板列表
// 2. 搜索和列表展示
// 3. 生成按钮打开参数配置弹窗
// 4. 生成成功后提供下载链接
```

**Verification:** 前端页面能展示 PPT 模板列表，点击生成能弹出参数配置。

---

### Task 8: 前端 — 启用导航节点

**Objective:** 从 `DISABLED_NODE_IDS` 中移除 `"analysis-ppt"`

**Files:**
- Modify: `src/app/components/NavigationTree.tsx`

**Step 1: 移除禁用**

```tsx
// 原: const DISABLED_NODE_IDS = new Set(["analysis-ppt"]);
// 改: const DISABLED_NODE_IDS = new Set([]);
```

**Verification:** 导航树中"智能演示PPT"节点可点击，点击后显示 AnalysisPPTContent 页面。

---

### Task 9: 集成测试

**Objective:** 端到端验证完整流程

**Steps:**

1. 创建一个测试 PPTX 模板（含 `{{ param:year }}`、`{{ metric:m_budget_actual_gap }}` 等占位符）
2. 通过 API 上传模板 → 确认变量被提取
3. 调用 generate API → 确认输出 .pptx 文件生成
4. 下载并检查 PPTX 内容是否正确替换
5. 前端展示模板列表 → 点击生成 → 下载

**Verification:** 完整流程无报错，输出 PPTX 中占位符被正确替换。

---

## 依赖确认

- [x] `python-pptx` 已在 `backend/requirements.txt` 中
- [x] 数据库表已存在（复用 smart_report 表族）
- [x] 前端 shadcn/ui 组件已安装

## Pitfalls

- PPTX 占位符可能跨 Run 分散（和 DOCX 一样的问题），需处理
- `_replace_text` 复用已有方法，需确认对 PPTX 的 Layout 段落也生效
- 模板文件扩展名校验需同时支持 .docx 和 .pptx
- `template_type` CHECK 约束可能需要 ALTER TABLE 迁移（如果已有 CHECK）

## 执行顺序

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
(后端基础 → 渲染 → API → 模板管理 → Preview → DB → 前端 → 启用 → 测试)
