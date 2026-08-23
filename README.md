# TaskFlow - 团队任务管理 API

[![CI](https://github.com/lengthharp-ctrl/taskflow/actions/workflows/ci.yml/badge.svg)](https://github.com/lengthharp-ctrl/taskflow/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)](https://www.postgresql.org/)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)]()

面向小团队的任务管理后端服务：注册登录、项目与成员管理、任务流转、评论系统，全部接口带 JWT 鉴权与项目成员级权限校验。

> 在线 Demo：[https://taskflow-api-eena.onrender.com](https://taskflow-api-eena.onrender.com)
>
> 在线接口文档：[https://taskflow-api-eena.onrender.com/docs](https://taskflow-api-eena.onrender.com/docs)
>
> （Render 免费层，15 分钟无请求会休眠，首次访问需冷启动约 30 秒）

![API 文档截图](docs/screenshots/docs.png)

## 技术栈

| 层级 | 技术 |
| --- | --- |
| Web 框架 | FastAPI |
| ORM | SQLAlchemy 2.0（异步 + asyncpg） |
| 数据库 | PostgreSQL |
| 迁移 | Alembic |
| 数据校验 | Pydantic v2 |
| 认证 | python-jose（JWT）+ passlib（bcrypt） |
| 测试 | Pytest + httpx（覆盖率 ≥ 80%） |
| 容器 | Docker + Docker Compose |
| 部署 | Render（免费层） |

## 功能特性

- 用户注册 / 登录 / JWT 访问令牌 + 刷新令牌
- 项目 CRUD、项目成员管理（管理员 / 普通成员两种角色）
- 任务 CRUD、状态流转（待办 → 进行中 → 已完成，可重新打开）
- 任务优先级（低 / 中 / 高 / 紧急）、截止日期、负责人
- 任务评论：发表、查看、修改（仅作者）、删除（作者或项目管理员）
- 任务按状态 / 负责人 / 优先级 / 关键字 / 截止日期筛选，支持分页与排序
- 权限校验：只有项目成员可访问项目数据，管理操作仅限管理员
- 统一响应格式 + 全局异常处理
- `/docs` 在线接口文档

## 项目亮点

- **两级权限模型**：项目创建者自动成为管理员；任务/评论操作要求项目成员，项目管理操作（改项目、加/移除成员）要求管理员，评论修改限作者、删除限作者或管理员——通过 FastAPI 依赖注入实现，校验逻辑集中、可复用。
- **任务状态机校验**：状态严格按 `待办 → 进行中 → 已完成` 推进，已完成可重新打开，非法流转直接返回 422，避免脏数据。
- **统一查询构建器**：`core/query.py` 封装了筛选（字段过滤 + 关键字搜索）、分页（offset/limit）、排序（多字段、前缀 `-` 倒序），所有列表接口复用同一套逻辑，新增资源零重复代码。
- **统一响应格式 + 全局异常处理**：所有接口返回 `{code, message, data}`，业务异常、HTTP 异常、校验异常统一拦截转换，前端对接成本低。
- **高测试覆盖率**：99 个测试用例，覆盖率 85%，覆盖正常 + 异常路径（未登录、无权限、参数错误、资源不存在、非法状态流转等）；默认内存 SQLite + function 级事务回滚保证用例隔离，支持切换 PostgreSQL 测试库。
- **工程化交付**：Docker 多阶段构建、Docker Compose 一键启动、Alembic 数据库迁移（upgrade/downgrade 双向验证）、Render Blueprint 一键部署（render.yaml 声明 Web Service + PostgreSQL + 环境变量）。

## 快速开始

### 环境要求

- Python 3.12+（本地开发）
- Docker + Docker Compose（推荐一键启动）
- 或直接使用 PostgreSQL 16 实例

### 本地运行（Docker Compose）

```bash
cp .env.example .env   # 修改 SECRET_KEY 等配置
docker compose up --build
```

启动后访问：

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 本地开发（不使用 Docker）

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# 准备 PostgreSQL 后执行迁移
alembic upgrade head

# 启动服务
uvicorn app.main:app --reload
```

### 环境变量配置

复制 `.env.example` 为 `.env` 并修改：

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `DATABASE_URL` | 异步 SQLAlchemy 连接串 | `postgresql+asyncpg://taskflow:taskflow@localhost:5432/taskflow` |
| `SECRET_KEY` | JWT 签名密钥（生产必改） | 足够长的随机字符串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 访问令牌有效期（分钟） | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 刷新令牌有效期（天） | `7` |
| `BACKEND_CORS_ORIGINS` | 允许的跨域来源，逗号分隔 | `https://a.com,https://b.com` |
| `DEBUG` | 是否开启调试 | `false` |

### 运行测试

```bash
pytest --cov=app --cov-report=term-missing
```

测试默认使用内存 SQLite 数据库（每个用例独立事务、自动回滚）；如需跑 PostgreSQL 测试库：

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://taskflow:taskflow@localhost:5432/taskflow_test
pytest
```

## API 文档

启动后访问 `/docs`（Swagger UI）或 `/redoc`。所有业务接口返回统一格式：

```json
{ "code": 0, "message": "ok", "data": { } }
```

错误时 `code` 为 HTTP 状态码，`message` 为可读错误信息：

| HTTP | code | 场景 |
| --- | --- | --- |
| 400 | 400 | 业务校验失败 |
| 401 | 401 | 未登录 / 令牌无效或过期 |
| 403 | 403 | 非项目成员 / 非管理员操作 |
| 404 | 404 | 资源不存在 |
| 409 | 409 | 数据冲突（重复注册、重复添加成员等） |
| 422 | 422 | 参数校验失败 |
| 500 | 500 | 服务器内部错误 |

### 接口一览

| 模块 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| 认证 | POST | `/api/v1/auth/register` | 注册（返回用户 + 令牌） |
| 认证 | POST | `/api/v1/auth/login` | 登录（用户名或邮箱） |
| 认证 | POST | `/api/v1/auth/refresh` | 刷新访问令牌 |
| 认证 | GET | `/api/v1/auth/me` | 当前用户 |
| 用户 | GET/PATCH | `/api/v1/users/me` | 我的资料 |
| 用户 | GET | `/api/v1/users/{user_id}` | 用户资料 |
| 项目 | POST | `/api/v1/projects` | 创建项目 |
| 项目 | GET | `/api/v1/projects` | 我参与的项目（分页） |
| 项目 | GET/PATCH/DELETE | `/api/v1/projects/{project_id}` | 项目详情 / 更新 / 删除（管理员） |
| 成员 | GET | `/api/v1/projects/{project_id}/members` | 成员列表 |
| 成员 | POST/PATCH/DELETE | `/api/v1/projects/{project_id}/members[...]` | 添加 / 改角色 / 移除（管理员） |
| 任务 | POST/GET | `/api/v1/projects/{project_id}/tasks` | 创建任务 / 任务列表（筛选分页排序） |
| 任务 | GET/PATCH/DELETE | `/api/v1/tasks/{task_id}` | 任务详情 / 更新 / 删除 |
| 任务 | PATCH | `/api/v1/tasks/{task_id}/status` | 状态流转 |
| 评论 | GET/POST | `/api/v1/tasks/{task_id}/comments` | 评论列表 / 发表评论 |
| 评论 | PATCH/DELETE | `/api/v1/comments/{comment_id}` | 修改（作者）/ 删除（作者或管理员） |

### 认证方式

登录 / 注册后拿到 `access_token`，请求头携带：

```http
Authorization: Bearer <access_token>
```

## 项目结构

```text
taskflow/
├── app/
│   ├── api/                  # 路由层
│   │   ├── auth.py           # 注册 / 登录 / 刷新 / 当前用户
│   │   ├── users.py          # 用户资料
│   │   ├── projects.py       # 项目 CRUD + 成员管理
│   │   ├── tasks.py          # 任务 CRUD + 筛选分页排序 + 状态流转
│   │   └── comments.py       # 评论
│   ├── core/
│   │   ├── config.py         # pydantic-settings 配置
│   │   ├── database.py       # 异步引擎与会话
│   │   ├── security.py       # 密码哈希 / JWT
│   │   ├── deps.py           # 当前用户 / 成员 / 管理员权限依赖
│   │   ├── exceptions.py     # 业务异常
│   │   ├── response.py       # 统一响应 + 分页结构
│   │   └── query.py          # 统一筛选 / 分页 / 排序
│   ├── models/               # SQLAlchemy 模型（user/project/task/comment）
│   ├── schemas/              # Pydantic 模型
│   └── main.py               # 应用入口 + 全局异常处理
├── alembic/                  # 数据库迁移
├── tests/                    # Pytest 测试（按模块）
├── Dockerfile                # 多阶段构建
├── docker-compose.yml        # web + postgres
├── render.yaml               # Render 部署配置
├── requirements.txt
└── README.md
```

## 数据库设计

```mermaid
erDiagram
    users ||--o{ project_members : "加入"
    projects ||--o{ project_members : "包含"
    users ||--o{ projects : "创建"
    projects ||--o{ tasks : "包含"
    users ||--o{ tasks : "负责"
    tasks ||--o{ comments : "评论"
    users ||--o{ comments : "发表"

    users {
        uuid id PK
        string email UK
        string username UK
        string hashed_password
        boolean is_active
    }
    projects {
        uuid id PK
        string name
        text description
        uuid owner_id FK
    }
    project_members {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        string role "admin | member"
    }
    tasks {
        uuid id PK
        uuid project_id FK
        string title
        string status "todo | in_progress | done"
        string priority "low | medium | high | urgent"
        uuid assignee_id FK
        datetime due_date
    }
    comments {
        uuid id PK
        uuid task_id FK
        uuid author_id FK
        text content
    }
```

## 部署（Render 免费层）

### 方式一：一键 Blueprint（推荐）

1. 将仓库推送到 GitHub；
2. Render 控制台 → New → Blueprint → 选择仓库；
3. 自动读取 `render.yaml`，创建 Web Service + PostgreSQL；
4. 首次部署完成后，访问 `https://<服务名>.onrender.com/docs` 验证。

### 方式二：手动创建

1. **PostgreSQL**：New → PostgreSQL（免费层），记下连接串；
2. **Web Service**：New → Web Service → 选仓库；
   - Build Command：`pip install -r requirements.txt`
   - Start Command：`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. 配置环境变量：`DATABASE_URL`、`SECRET_KEY`（面板生成）、`BACKEND_CORS_ORIGINS`；
4. 部署后访问 `/docs`。

> 注意：Render 免费 PostgreSQL 约 90 天过期，建议到期前用 `pg_dump` 导出备份，再创建新实例并迁移。
>
> 提示：Render 免费层 Web Service 约 15 分钟无请求会进入休眠，下次访问需要冷启动约 30 秒，属正常现象。

## 后续优化

- 刷新令牌落库 + 吊销机制（登出 / 强制下线）
- 任务活动日志 / 操作审计
- 邮件通知与截止日期提醒
- WebSocket 实时评论与任务看板
- 附件上传（S3 / R2）
- 前端管理台（可复用同一套接口）
- 接口限流与更细粒度的权限模型
