# 智能笔记 (AI Note)

一个基于 DeepSeek AI 驱动的云笔记应用，支持中文全文搜索、分类管理、AI 辅助写作和多模型配置。

## 项目状态

- **后端**：功能基本完善（认证、分类/笔记 CRUD、AI 配置、图片上传）
- **前端**：Vue 3 脚手架已搭建，依赖已安装，尚未完成组件和路由的 wiring
- **AI 集成**：模型配置和管理端点就绪，核心 AI 服务调用尚未实现

## 技术栈

### 后端

- **Python 3.12+**
- **FastAPI 0.137** — 异步 Web 框架
- **SQLAlchemy 2.0** + **asyncpg** — 异步 ORM 和 PostgreSQL 驱动
- **Pydantic v2** — 数据校验和序列化
- **PyJWT 2.13** + **bcrypt 5.0** — JWT 认证和密码哈希
- **jieba 0.42** — 中文分词，用于 PostgreSQL 全文搜索
- **OpenAI SDK 2.41** — AI 模型调用
- **Uvicorn 0.49** — ASGI 服务器

### 前端

- **Vue 3.5** + **Vite 8** + **TypeScript 6**
- **Tailwind CSS v4** — 原子化 CSS
- **Naive UI** — Vue 3 组件库
- **Pinia 3** — 状态管理
- **Vue Router 5** — 路由管理
- **Axios** — HTTP 客户端
- **vditor** + **highlight.js** — Markdown 编辑器与语法高亮
- **vuedraggable** / **sortablejs** — 拖拽排序
- **VueUse** — 组合式工具集
- **dayjs** — 日期处理

### 数据库

- **PostgreSQL** — 主数据库（支持中文全文搜索、JSONB、TSVECTOR）
- **SQLite** — 缓存层（预留）

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- PostgreSQL 14+
- Git Bash（Windows）或兼容的 POSIX shell

### 1. 克隆项目并创建配置文件

```bash
git clone <repository-url>
cd assistant_note
cp .env.example .env
# 编辑 .env 填写数据库连接信息和 JWT 密钥等敏感配置
```

### 2. 初始化数据库

```bash
# 创建 PostgreSQL 数据库后，按顺序执行迁移脚本
psql -U <user> -d <database> -f migration/001_init_tables.sql
psql -U <user> -d <database> -f migration/002_partial_unique_and_tags_index.sql
psql -U <user> -d <database> -f migration/003_ai_model_and_config.sql
psql -U <user> -d <database> -f migration/004_roles_and_user_role.sql
```

### 3. 启动后端

```bash
# 创建并激活虚拟环境
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器（端口 6581）
uvicorn backend.main:app --host 0.0.0.0 --port 6581 --reload
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev  # 端口 6580
```

### 5. 访问应用

- 前端界面：`http://localhost:6580`
- 后端 API：`http://localhost:6581`
- API 文档：`http://localhost:6581/docs`（Swagger UI）

## 项目结构

```
.
├── backend/                    # 后端源码
│   ├── main.py                 # FastAPI 入口
│   ├── apps/
│   │   ├── api/                # API 端点定义
│   │   ├── model/              # SQLAlchemy ORM 模型
│   │   ├── router/             # 路由注册
│   │   ├── service/            # 业务逻辑层
│   │   ├── ai/tools/           # AI 工具注册
│   │   └── utils/              # 工具模块（数据库、安全、日志等）
│   └── ...
├── frontend/                   # 前端源码
│   ├── src/
│   │   ├── main.ts             # 应用入口（当前为空挂载）
│   │   ├── App.vue             # 根组件（当前为空）
│   │   └── style.css           # Tailwind 主题变量
│   └── package.json
├── migration/                  # 数据库迁移脚本（原始 SQL）
├── .env.example                # 环境变量模板
├── requirements.txt            # Python 依赖
└── README.md
```

## 核心功能

### 已实现

- **用户认证**：JWT + bcrypt，支持注册/登录/Token 刷新
- **分类管理**：树形结构，支持层级嵌套、软删除
- **笔记管理**：Markdown 内容、标签、置顶、字数统计
- **中文全文搜索**：基于 jieba 分词 + PostgreSQL tsvector
- **图片上传**：拖拽/粘贴上传，支持常见图片格式
- **AI 对话**：支持 OpenAI 和 Anthropic 格式模型的流式对话，工具调用（笔记搜索、标签搜索、读写笔记等），SSE 实时推送
- **AI 模型配置**：多模型池（OpenAI/Anthropic 格式），DB 存储配置，支持工具注册和运行时参数
- **AI 工具注册**：笔记搜索、标签搜索等可调用工具
- **角色权限**：普通用户 / 管理员双角色，admin 端点受保护
- **日志追踪**：请求级 trace_id，按日期+大小轮转日志

### 待实现

- 前端页面和路由 wiring
- 笔记历史版本
- 数据导入/导出

## 设计决策

- **全 GET/POST API**：所有端点仅使用 GET（读取）和 POST（写入），更新用 `POST /{id}/update`，删除用 `POST /{id}/delete`
- **Snowflake ID**：应用层生成 64 位分布式 ID，JSON 序列化为字符串避免 JavaScript 精度丢失
- **软删除**：分类和笔记使用 `is_deleted` 标志，查询自动过滤
- **无数据库外键**：关系在应用层维护，迁移使用原始 SQL
- **滑动 Token 刷新**：每次请求返回新 access token，2 小时窗口自动续期

## 开发注意事项

- `.env` 已加入 `.gitignore`，切勿提交敏感信息
- 虚拟环境位于 `.venv/`，所有 Python 操作需先激活
- 数据库迁移在 `migration/` 目录下，无 Alembic，需手动按序执行
- 前端依赖已安装但尚未导入使用，需自行完成组件和状态管理 wiring

## License

MIT
