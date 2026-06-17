#!/usr/bin/env bash
# ============================================================================
# package_deploy.sh — 一键打包银行预算系统部署包
#
# 用法:
#   bash .agents/skills/qoder-deploy-package/scripts/package_deploy.sh              # 默认打包
#   bash .agents/skills/qoder-deploy-package/scripts/package_deploy.sh --skip-data  # 不含数据库文件（体积更小）
#   bash .agents/skills/qoder-deploy-package/scripts/package_deploy.sh --skip-env   # 不含 .env（需手动创建）
#
# 产物: archive/releases/qoder-banking-budget-<日期>.zip
# ============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../../.." && pwd)"
OUTPUT_DIR="$ROOT_DIR/archive/releases"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PKG_NAME="qoder-banking-budget-${TIMESTAMP}"
ZIP_FILE="$OUTPUT_DIR/$PKG_NAME.zip"
SKIP_DATA=0
SKIP_ENV=0

for arg in "$@"; do
    case "$arg" in
        --skip-data) SKIP_DATA=1 ;;
        --skip-env)  SKIP_ENV=1 ;;
    esac
done

echo "============================================"
echo "  银行预算系统 — 部署打包工具"
echo "============================================"
echo ""
echo "项目根目录: $ROOT_DIR"
echo "输出文件:   $ZIP_FILE"
echo "跳过数据库: $([ $SKIP_DATA -eq 1 ] && echo '是' || echo '否')"
echo "跳过 .env:  $([ $SKIP_ENV -eq 1 ] && echo '是' || echo '否')"
echo ""

mkdir -p "$OUTPUT_DIR"
rm -f "$ZIP_FILE"

# ---- 直接从源目录追加到 zip（省去临时复制占空间） ----
# 使用 -j 选项避免将 .gitignore 等的绝对路径写进去
# 所有文件统一放在 $PKG_NAME/ 前缀下

cd "$ROOT_DIR"

# ---- 0. 预构建前端 ----
echo "[0/8] 预构建前端 (npm run build)..."
cd "$ROOT_DIR/apps/web"
npm run build 2>&1 | tail -3
cd "$ROOT_DIR"
if [ ! -d apps/web/dist ]; then
    echo "❌ 前端构建失败，dist/ 不存在！"
    exit 1
fi

# ---- 1. 后端代码 + 测试 + 锁文件 ----
echo "[1/8] 打包后端代码（含测试 + uv.lock）..."
zip -rq "$ZIP_FILE" \
    apps/api/app/ \
    apps/api/scripts/ \
    apps/api/run_server.py \
    apps/api/pyproject.toml \
    -x '*.pyc' '*__pycache__*'
# 测试文件
[ -d apps/api/tests ] && zip -rq "$ZIP_FILE" apps/api/tests/ -x '*.pyc' '*__pycache__*'
# 可选文件
[ -f apps/api/requirements.txt ] && zip -q "$ZIP_FILE" apps/api/requirements.txt
[ -f apps/api/.python-version ]  && zip -q "$ZIP_FILE" apps/api/.python-version
[ -f apps/api/uv.lock ]          && zip -q "$ZIP_FILE" apps/api/uv.lock
[ -f apps/api/.env.example ]     && zip -q "$ZIP_FILE" apps/api/.env.example

# ---- 2. 前端代码（源码 + 预构建产物） ----
echo "[2/8] 打包前端代码（含 dist/ 预构建产物）..."
zip -rq "$ZIP_FILE" \
    apps/web/src/ \
    apps/web/dist/ \
    apps/web/vite.config.ts \
    -x '*node_modules*'
# 前端配置文件（必须齐全，否则 build/样式全挂）
for f in apps/web/package.json apps/web/package-lock.json \
         apps/web/tsconfig.json apps/web/tsconfig.app.json \
         apps/web/tsconfig.node.json \
         apps/web/index.html \
         apps/web/tailwind.config.cjs apps/web/tailwind.config.js \
         apps/web/postcss.config.cjs apps/web/postcss.config.js; do
    [ -f "$f" ] && zip -q "$ZIP_FILE" "$f"
done
[ -d apps/web/public ] && zip -rq "$ZIP_FILE" apps/web/public/
# Playwright e2e 测试
[ -d apps/web/e2e ] && zip -rq "$ZIP_FILE" apps/web/e2e/

# ---- 3. 资源文件 + 根级 npm workspace + 文档 ----
echo "[3/8] 打包资源文件 + 文档 + 根级 npm 配置..."
zip -rq "$ZIP_FILE" resources/
# 根级 package.json / package-lock.json（monorepo workspace 必需）
[ -f package.json ] && zip -q "$ZIP_FILE" package.json
[ -f package-lock.json ] && zip -q "$ZIP_FILE" package-lock.json
# docs/ 文档目录
[ -d docs ] && zip -rq "$ZIP_FILE" docs/

# ---- 4. 数据库 ----
if [ $SKIP_DATA -eq 0 ]; then
    echo "[4/8] 打包数据库文件..."
    for db in var/data/*.db; do
        [ -f "$db" ] && zip -q "$ZIP_FILE" "$db"
    done
    # 子目录（模板等）
    for subdir in var/data/*/; do
        [ -d "$subdir" ] && zip -rq "$ZIP_FILE" "$subdir"
    done
else
    echo "[4/8] 跳过数据库文件 (--skip-data)"
fi

# ---- 5. 配置文件 ----
echo "[5/8] 打包配置文件..."

if [ $SKIP_ENV -eq 0 ]; then
    if [ -f apps/api/.env ]; then
        zip -q "$ZIP_FILE" apps/api/.env
        echo "       ✓ 已包含 apps/api/.env（含密钥，请妥善保管部署包）"
    else
        echo "       ⚠ 未找到 apps/api/.env，将使用 .env.example"
        [ -f apps/api/.env.example ] && zip -q "$ZIP_FILE" apps/api/.env.example
    fi
else
    echo "       跳过 .env (--skip-env)，请部署时手动创建"
    [ -f apps/api/.env.example ] && zip -q "$ZIP_FILE" apps/api/.env.example
fi

# 启停脚本 & gitignore
zip -q "$ZIP_FILE" start.sh stop.sh .gitignore

# ---- 6. 生成部署说明（临时文件，加入 zip 后删除） ----
echo "[6/8] 生成部署说明..."
DEPLOY_GUIDE="$ROOT_DIR/tmp_deploy_guide_$$.md"
cat > "$DEPLOY_GUIDE" << 'DEPLOY_EOF'
# 银行预算系统 — 服务器部署指南

## 前置条件

- Python 3.11+（推荐 3.12）
- Node.js 18+（推荐 20 LTS）
- npm 9+
- 服务器可访问内网（飞书/DeepSeek API 需要）

## 快速部署（3 步）

> 前端已预构建，无需在服务器上 npm install / npm run build！

### 第 1 步：上传并解压

```bash
# 将部署包上传到服务器
scp qoder-banking-budget-*.zip user@your-server:/opt/

# 登录服务器后解压
ssh user@your-server
cd /opt
unzip qoder-banking-budget-*.zip
mv qoder-banking-budget-* banking-budget
cd banking-budget
```

### 第 2 步：配置环境变量 + 安装后端依赖

```bash
# 编辑后端配置（最关键！）
vim apps/api/.env
```

必须确认的配置项：

| 变量 | 说明 | 示例 |
|------|------|------|
| `CORS_ORIGINS` | 允许的前端访问地址 | `http://your-server:8443,http://your-server` |
| `CORS_ORIGIN_REGEX` | 跨域正则匹配 | `^http://10[.]65[.]\d{1,3}[.]\d{1,3}:8443$` |
| `DEEPSEEK_API_KEY` | DeepSeek AI 密钥 | `sk-xxxx` |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com` |
| `FEISHU_ENABLED` | 是否启用飞书 | `true` / `false` |
| `FEISHU_APP_ID` | 飞书应用 ID | `cli_xxxxxx` |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | `xxxxxx` |

安装后端依赖：

```bash
cd apps/api

# 方式一：使用 uv（推荐，更快）
pip install uv 2>/dev/null || pip3 install uv
uv sync

# 方式二：使用 pip + venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ../..
```

### 第 3 步：启动服务

```bash
bash start.sh
```

服务启动后：
- 后端 API：`http://your-server:8009`
- 前端界面：`http://your-server:8443`
- API 文档：`http://your-server:8009/docs`

## 常用运维命令

```bash
bash start.sh          # 启动
bash stop.sh           # 停止
tail -f var/logs/backend.log   # 查看后端日志
tail -f var/logs/frontend.log  # 查看前端日志
bash stop.sh && bash start.sh  # 修改配置后重启
```

## 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 8009 | FastAPI 后端 | API 服务 |
| 8443 | Vite 前端 | 开发服务器（代理 /api 到后端） |

## 故障排查

| 问题 | 解决方法 |
|------|----------|
| 端口被占用 | `lsof -tiTCP:8009` 找到进程后 `kill` |
| 前端无法连接后端 | 检查 `.env` 中 CORS 配置和 Vite proxy |
| 飞书连接失败 | 确认服务器能访问 `open.feishu.cn` |
| npm install 失败 | 检查 Node.js 版本，或使用离线 node_modules |
| Python 版本不对 | `python3 --version` 确认 >= 3.11 |
DEPLOY_EOF

# 将部署说明加入 zip（放在根目录）
cd "$ROOT_DIR"
zip -qj "$ZIP_FILE" "$DEPLOY_GUIDE"
# 重命名为 DEPLOY_GUIDE.md
python3 -c "
import zipfile, os, tempfile
zf = zipfile.ZipFile('$ZIP_FILE', 'a')
# 找到临时文件名的 entry，读取内容，以 DEPLOY_GUIDE.md 写入
basename = os.path.basename('$DEPLOY_GUIDE')
# zip 里已有该临时文件名条目，需要用新文件名重新写入
with open('$DEPLOY_GUIDE', 'rb') as f:
    data = f.read()
# 删除旧临时条目并添加新名：直接追加即可，解压时同名覆盖
# 更简洁做法：单独创建一个干净的临时 zip
"
# 简化：直接用 python 处理重命名
python3 << PY_EOF
import zipfile, shutil, os
src = "$ZIP_FILE"
tmp = src + ".tmp"
basename = os.path.basename("$DEPLOY_GUIDE")
with zipfile.ZipFile(src, 'r') as zin:
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == basename:
                item.filename = "DEPLOY_GUIDE.md"
            zout.writestr(item, data)
shutil.move(tmp, src)
PY_EOF

rm -f "$DEPLOY_GUIDE"

# ---- 7. 生成 requirements.txt（确保最新） ----
echo "[7/8] 生成 requirements.txt..."
REQ_TMP="$ROOT_DIR/tmp_requirements_$$.txt"
if command -v uv >/dev/null 2>&1 && [ -f apps/api/uv.lock ]; then
    uv export --no-flags --no-hashes > "$REQ_TMP" 2>/dev/null || true
    if [ -s "$REQ_TMP" ]; then
        # 替换 zip 中的 requirements.txt
        python3 << PY_EOF
import zipfile, shutil
src = "$ZIP_FILE"
tmp = src + ".tmp"
with zipfile.ZipFile(src, 'r') as zin:
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "apps/api/requirements.txt":
                with open("$REQ_TMP", 'rb') as f:
                    data = f.read()
                zout.writestr(item, data)
            else:
                zout.writestr(item, zin.read(item.filename))
shutil.move(tmp, src)
PY_EOF
    fi
fi

# ---- 8. 完整性校验 ----
echo "[8/8] 完整性校验..."
CHECK_PASS=1
for item in "apps/web/dist/index.html" "apps/web/tailwind.config.cjs" \
           "apps/web/postcss.config.cjs" "apps/web/tsconfig.node.json" \
           "package.json" "package-lock.json" \
           "apps/api/.env" "apps/api/.env.example" \
           "apps/api/uv.lock" "apps/api/tests/" \
           "apps/web/e2e/" "docs/" \
           "start.sh" "stop.sh" "DEPLOY_GUIDE.md"; do
    if python3 -c "import zipfile; z=zipfile.ZipFile('$ZIP_FILE'); matches=[n for n in z.namelist() if n.endswith('$item')]; exit(0 if matches else 1)" 2>/dev/null; then
        echo "  ✓ $item"
    else
        echo "  ❌ $item 缺失！"
        CHECK_PASS=0
    fi
done
if [ $CHECK_PASS -eq 0 ]; then
    echo ""
    echo "⚠ 部署包校验未通过，请检查上述缺失项！"
fi

# ---- 将所有文件移到 $PKG_NAME/ 前缀下 ----
echo "[final] 调整 zip 内目录结构..."
python3 << PY_EOF
import zipfile, shutil
src = "$ZIP_FILE"
tmp = src + ".tmp"
prefix = "$PKG_NAME/"
with zipfile.ZipFile(src, 'r') as zin:
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            item.filename = prefix + item.filename
            zout.writestr(item, data)
shutil.move(tmp, src)
PY_EOF

# ---- 完成 ----
COMPRESS_SIZE=$(du -sh "$ZIP_FILE" | cut -f1)

echo ""
echo "============================================"
echo "  部署包已生成！"
echo "============================================"
echo ""
echo "  文件: $ZIP_FILE"
echo "  大小: $COMPRESS_SIZE"
echo ""
echo "  上传到服务器:"
echo "    scp $ZIP_FILE user@server:/opt/"
echo ""
echo "  服务器上解压部署:"
echo "    cd /opt && unzip $(basename $ZIP_FILE)"
echo "    cd $PKG_NAME"
echo "    vim apps/api/.env    # 修改环境变量"
echo "    bash start.sh         # 启动服务"
echo ""

# 清理临时文件
rm -f "$REQ_TMP"
