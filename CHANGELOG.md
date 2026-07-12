# 工作日志 (Changelog)

Eduflow 学员管理系统 — 变更记录

---

## [v2.1] — 2026-07-12 · 安全加固与 Bug 修复

### 🔴 安全修补 (Critical)

**S1 · 修复路径穿越漏洞** (`app.py` serve_static, 行 468–502)
- 静态文件根目录由 `ASSETS_DIR` 改为 `STATIC_DIR`
- 新增 `os.path.realpath` 归一化 + containment 校验，越界文件一律 404
- 剥离 `/static/` 前缀后做 join，防止 `../` 穿越
- 验证：`/static/../data/database.sqlite` → 404, `/static/../app.py` → 404

**S2 · 绑定回环地址** (`app.py` run_server, 行 1481)
- 监听地址 `0.0.0.0` → `127.0.0.1`
- 本地离线应用无需暴露内网，与 S1 配合缩小攻击面

**S3 · 安全声明** (`README.md`)
- 新增醒目安全提示：当前无用户鉴权，仅限本地单机使用，禁止公网部署

### 🔧 Bug 修复

**毕业届次计算不一致** (`database.py` migrate_db, 行 64–70)
- `graduation = (cohort + 2) % 100` → `compute_graduation_year(cohort)`
- 统一使用 cohort + 3（高中三年制），与 `create_student` 主逻辑一致
- 注意陷阱：`compute_graduation_year` 返回字符串 `'29'`，不能套 `f'{graduation:02d}'`
- 验证：26级→29届, 25级→28届, 24级→27届

**Query 参数 int 转换无保护** (`app.py` 多处)
- 新增 `AppHandler._safe_int(value, default=0)` 静态方法
- 替换 8 处裸 `int()` 调用：
  - `students_page` — page 参数
  - `grades_page` — class_id / student_id 参数
  - `assignments_page` — class_id 参数
  - `attendances_page` — class_id 参数
  - `payments_page` — student_id 参数
  - `grades_export` — class_id 参数
  - `class_students_manage` — student_id（表单/查询）
  - `attendance_save` — key.replace('status_', '') 解析
- 非数字输入（如 ?page=abc）不再触发 500，安全降级为默认值

### 📦 可移植性

**package.json** (行 7–8)
- `start`/`seed` 脚本路径由开发者机器绝对路径 → 通用 `python3`
- 分发后 `npm start` 可在任何安装 Python 3.9+ 的机器运行

**overview.md** (行 55–57)
- 同步去除硬编码路径

**README.md**
- 补充环境要求：Python 3.9+（推荐 3.10+）

### 🧹 工作空间清理

| 操作 | 目标 | 原因 |
|------|------|------|
| 删除 | `2026-07-04-08-49-52/`（14 文件） | 项目副本，与根目录完全重复 |
| 删除 | `memory/`（2 文件） | 误置的记忆目录（正确定位在 .workbuddy/memory/） |
| 删除 | `generated-images/`（3 图片） | AI 生成临时文件 |
| 删除 | `student-system-windows.zip` | 构建产物 |
| 删除 | `data/database.sqlite.bak.*` | 含学员 PII 的数据库备份 |
| 更新 | `.gitignore` | 新增 `*.sqlite`、`*.zip`、`data/*.bak.*`、`generated-images/` |
| git rm | `data/database.sqlite` | 已入库的 PII 数据库，从版本库移除（保留本地文件） |
| git rm | `student-system-windows.zip` | 构建产物，从版本库移除 |

### ✨ 功能增强（参考 Edutrack）

**仪表盘** (`templates/index.html`)
- 近期课程卡片新增上课方式标识（线上/线下/混合同步 badge）
- 底部新增「快捷操作」区域：添加学员、新建班级、排课、成绩/作业/缴费快捷入口

**工程化文件就绪**
- `pyproject.toml` — ruff / mypy / bandit / pytest 配置
- `.pre-commit-config.yaml` — pre-commit hooks 配置
- `.github/workflows/code-review.yml` — CI 代码审查流水线
- `docs/PR_TEMPLATE.md` — MR 模板
- `docs/REVIEW_CHECKLIST.md` — 代码审查清单
- `代码审查标准与流程.md` — 审查规范（8 维度）
- `代码审查报告.md` — 本次审查详细报告
- `代码修复任务提示词.md` — 自包含的修复任务说明

### 🧪 验收结果

| 验收项 | 结果 |
|--------|------|
| 路径穿越 `/static/../data/database.sqlite` → 404 | ✅ |
| 路径穿越 `/static/../app.py` → 404 | ✅ |
| 正常静态资源 `/static/css/style.css` → 200 | ✅ |
| 首页 `/` → 200 | ✅ |
| 毕业届次 26级→29届 | ✅ |
| `python3 -m py_compile app.py` 语法检查 | ✅ |
| `python3 -m py_compile database.py` 语法检查 | ✅ |

### ⚠️ 已知遗留 TODO

| 优先级 | 事项 | 说明 |
|--------|------|------|
| 🟡 | 补单测 | `database.py` 纯函数（compute_graduation_year, _to_int, CSV 解析）覆盖率为 0 |
| 🟡 | 接 pre-commit + CI | `pyproject.toml` 和 `.pre-commit-config.yaml` 已就绪，需接入仓库 |
| 🟡 | 跑 ruff 清理存量 | pyproject.toml 有 ruff 配置，未执行过 |
| 🟢 | 拆分 app.py / database.py | 单文件过大（~1500行），长期可考虑按业务域拆模块 |
| 🟢 | API 接口文档 | /api/* 路由暂无文档说明 |

---

## [v2.0] — 2026-07-04 · 功能升级

- 重写模板引擎：完整支持 if/elif/else、for、include 嵌套
- 新增学员批量操作：批量加入班级、修改信息、CSV 批量导入
- 线上线下同步机制：课程上课方式（线下/线上/混合同步）+ 考勤参与方式
- 学员按"级"管理：级次字段、自动计算毕业届次
- 成绩管理优化：按班级分组展示、CSV 导入导出
- 作业管理：提交状态编辑、成绩导入、按均分排序
- 打包分发：PyInstaller 打包为独立可执行程序

---

> 格式说明：版本号按 [SemVer](https://semver.org/lang/zh-CN/) 风格 —— `主版本.次版本.修订号`。每次迭代独立记录，下方递增。
