# 飞书机器人（预算智能体）

## 依赖

- Python 包：`lark-oapi`（见 `backend/requirements.txt`）
- 运行环境需能访问公网 `open.feishu.cn`（长连接出站）

## 配置（`backend/.env`）

| 变量 | 说明 |
|------|------|
| `FEISHU_ENABLED` | `true` 时启动长连接客户端 |
| `FEISHU_APP_ID` | 企业自建应用 App ID |
| `FEISHU_APP_SECRET` | 应用 Secret |
| `FEISHU_DOMAIN` | 默认 `https://open.feishu.cn`；国际版 Lark 用 `https://open.larksuite.com` |
| `FEISHU_INSECURE_SSL` | `true` 时跳过 WSS 证书校验（仅内网/排障；公司代理导致 `CERTIFICATE_VERIFY_FAILED` 时可开；生产勿用） |

## 飞书开发者后台

1. 创建**企业自建应用**（长连接仅支持自建应用）。
2. 开启**机器人**能力；在「事件与回调」中选择**使用长连接接收事件**，并订阅 **`im.message.receive_v1`**（接收消息 v2.0）。
3. 为应用申请所需权限（至少包含接收与发送单聊/群聊消息相关 IM 权限，以控制台实际清单为准）。
4. 发布应用版本，将机器人拉入对话或单聊。

## 用户绑定

- **自助**：在飞书中向机器人发送：  
  `绑定 系统用户名 日常登录密码`  
  （密码中请勿含空格；与 Web 端日常密码一致。）
- **管理员**：登录 Web 后调用 `GET/POST/DELETE /api/system/feishu/bindings`（需**全权管理员**权限，`/api/system` 要求 permission 3）。

绑定数据表：`common.db` 中的 `feishu_user_binding`（`open_id` → `user_id`）。

## 行为说明

- 进程内启动**独立守护线程**运行飞书 WebSocket 客户端；事件回调内只做轻量逻辑，智能体在后台线程中执行并通过「回复消息」接口应答。
- **多实例部署**：飞书长连接为集群随机投递，同一应用多进程各建连接会导致事件只到其中一个实例；生产环境应单实例跑机器人或改用 Webhook + 公网地址。

## 相关代码

- `backend/app/feishu_bot.py`：长连接、消息处理、调用 `AgentGraphService.chat`
- `backend/app/feishu_store.py`：绑定存储与校验
- `backend/app/main.py`：`lifespan` 中启动机器人；`/api/system/feishu/bindings` 管理接口
