# EduFlow

面向教培行业的本地学员管理工具。零外部 Python 依赖，标准库实现，支持 macOS / Windows / Linux。

> ⚠️ **安全声明**：当前版本无用户鉴权机制，**仅限本地单机使用**（绑定 127.0.0.1），禁止部署到公网或内网共享环境。

## 功能模块

| 模块 | 说明 |
|------|------|
| 仪表盘 | 学员数/班级数/课程数/欠费统计 + 近期课程提醒 |
| 学员管理 | CRUD + 搜索/分页/按级次筛选/CSV 批量导入/批量操作/学习追踪 |
| 班级管理 | 增删改查 + 学员分配（支持搜索添加）+ 课程关联 |
| 课程管理 | 排课 + 线上/线下/同步方式 + 出勤签到 |
| 成绩管理 | 按班级分组展示 + 分布图 + CSV 导入导出 |
| 作业管理 | 提交状态编辑 + CSV 成绩导入 + 按均分排序 |
| 出勤记录 | 按班级筛选 + 参与方式（线上/线下） |
| 缴费管理 | 学费/教材/其他 + 欠费逾期标记 |
| 学习追踪 | 作业成绩趋势折线图（Chart.js）+ 均分参考线 |

## 快速启动

> **环境要求**：Python 3.9+（推荐 3.10+）

```bash
# 生成示例数据
python3 seed.py

# 启动服务
python3 app.py

# 浏览器打开
open http://localhost:3000
```

启动后自动打开浏览器。首次运行自动创建数据库，无需手动配置。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 标准库：`http.server` + `sqlite3`（多线程） |
| 前端 | 原生 HTML/CSS/JS + Chart.js |
| 模板 | 自研 AST 模板引擎（支持 if/for/include） |
| 打包 | PyInstaller → 独立可执行程序 |

**零外部 Python 依赖**，无需 `pip install`。打包后的可执行文件内置 Python 运行时。

## 打包发布

### macOS / Linux

```bash
pip install pyinstaller
pyinstaller Eduflow.spec --clean
# 输出：dist/EduFlow
```

### Windows

```bash
# 1. 安装 Python 3.9+（python.org）
# 2. 双击运行
build_windows.bat

# 输出：dist/EduFlow.exe
```

首次运行 macOS 打包程序若提示"无法验证开发者"：`xattr -dr com.apple.quarantine dist/EduFlow`

详细文档见：[PROJECT.md](PROJECT.md) | [使用说明](使用说明.md) | [工作日志](CHANGELOG.md)

## 许可

[CC BY-NC-SA 4.0](LICENSE) — 署名-非商业性使用-相同方式共享。允许自由使用、修改和分享，但禁止商业用途，使用时必须注明来源。
