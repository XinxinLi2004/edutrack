# EduFlow — 项目文档

> 版本 v2.0 | 2026-07-08 | 零外部依赖 · 本地离线运行

---

## 1. 项目概览

**EduFlow** 是一个面向教培行业的本地学员管理工具，支持学员档案、班级管理、课程排期、成绩分析、作业跟踪、出勤记录和缴费管理等核心教务功能。

### 技术栈

| 层级  | 技术                            | 说明                                                  |
| --- | ----------------------------- | --------------------------------------------------- |
| 后端  | Python 3.13 标准库 `http.server` | 多线程 HTTP 服务器（ThreadingMixIn）                        |
| 数据库 | SQLite 3                      | 单文件数据库，WAL 模式，外键约束                                  |
| 模板  | 自研 AST 模板引擎                   | 支持 `if/elif/else`、`for`、`include` 嵌套、`\|length` 过滤器 |
| 前端  | 原生 HTML/CSS/JS + Chart.js     | 玻璃拟态 UI、明暗主题切换、响应式布局                                |

### 核心特点

- **零外部依赖**：仅需 Python 3.9+，无需 pip install
- **本地离线**：所有数据存储在本地 `data/database.sqlite`
- **一键部署**：复制文件夹即可运行，支持 PyInstaller 打包为独立可执行程序
- **多线程服务**：并发处理浏览器请求，页面秒开

---

## 2. 快速开始

### 开发模式

```bash
# 1. 生成测试数据（仅首次）
python3 seed.py

# 2. 启动服务器
python3 app.py

# 3. 浏览器访问
open http://localhost:3000
```

### 打包版本

```bash
# 双击运行或终端启动
./dist/EduFlow

# macOS 安全提示处理
xattr -dr com.apple.quarantine "dist/EduFlow"
```

### 数据备份

复制 `data/database.sqlite` 文件即可完整备份所有数据。

---

## 3. 项目目录结构

```
├── app.py                     # 主程序入口（~1455行）
├── database.py                # 数据库操作层（~1544行）
├── seed.py                    # 测试数据生成（~217行）
├── student-system.spec        # PyInstaller 打包配置
├── data/
│   └── database.sqlite        # SQLite 数据库文件
├── static/
│   ├── css/style.css          # 样式文件（~795行）
│   └── js/app.js              # 前端脚本（~118行）
├── templates/
│   ├── index.html             # 仪表盘
│   ├── partials/              # 公共组件
│   │   ├── header.html        # 头部 + 侧边栏 + SVG图标库
│   │   ├── footer.html        # 尾部闭合标签
│   │   └── error.html         # 错误页
│   ├── students/              # 学员模块（7个模板）
│   ├── classes/               # 班级模块（3个模板）
│   ├── courses/               # 课程模块（3个模板）
│   ├── grades/                # 成绩模块（4个模板）
│   ├── assignments/           # 作业模块（5个模板）
│   ├── attendances/           # 出勤模块（1个模板）
│   └── payments/              # 缴费模块（2个模板）
├── dist/
│   ├── EduFlow    # 打包后的可执行程序
│   └── data/database.sqlite   # 运行时数据库
└── build/                     # PyInstaller 构建中间文件
```

---

## 4. 核心文件说明

---

### 4.1 app.py — 主程序入口（~1455行）

#### 4.1.0 环境适配（第18-35行）

```python
if getattr(sys, 'frozen', False):
    ASSETS_DIR = getattr(sys, '_MEIPASS', ...)  # PyInstaller 打包后的临时解压目录
    DATA_DIR = os.path.dirname(sys.executable)   # 可执行文件所在目录（用于读写数据库）
else:
    ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = ASSETS_DIR
```

`ASSETS_DIR` 用于读取只读资源（模板、静态文件）；`DATA_DIR` 用于读写数据文件（数据库）。

---

#### 4.1.1 模板引擎（第40-350行）

自定义 AST 模板引擎，完整实现 Jinja2 核心子集。

##### 节点类

| 类             | 行号  | 说明                                            |
| ------------- | --- | --------------------------------------------- |
| `TextNode`    | 44  | 纯文本节点，`render()` 返回原文                         |
| `VarNode`     | 52  | 变量节点，支持 `\|length` 过滤器和 `\|default:'xxx'` 默认值 |
| `IfNode`      | 73  | 条件节点，支持 if / elif / else 分支                   |
| `ForNode`     | 85  | 循环节点，暴露 `forloop` 对象                          |
| `IncludeNode` | 105 | 包含其他模板，参数透传                                   |

##### 解析函数

| 函数                                 | 行号  | 说明                             |
| ---------------------------------- | --- | ------------------------------ |
| `tokenize(content)`                | 113 | 正则切分 `{% %}` 标签和 `{{ }}` 变量    |
| `parse_var(expr)`                  | 134 | 解析变量表达式，支持 `\|` 管道分隔           |
| `parse_if(tokens, i)`              | 148 | 解析 if/elif/else/endif 块        |
| `parse_for(tokens, i)`             | 183 | 解析 for/in/endfor 循环            |
| `parse_include(tok_val)`           | 197 | 解析 `{% include "name.html" %}` |
| `parse_token(tokens, i)`           | 207 | 分发解析                           |
| `parse_nodes(tokens, i, end_tags)` | 231 | 顺序解析直到结束标签                     |

##### 渲染函数

| 函数                             | 行号  | 说明                                                       |
| ------------------------------ | --- | -------------------------------------------------------- |
| `render_template(name, **ctx)` | 252 | 渲染模板入口，含文件修改时间缓存（修改模板自动刷新）                               |
| `evaluate_nodes(nodes, ctx)`   | 247 | 渲染节点列表                                                   |
| `get_value(expr, ctx)`         | 272 | 点号表达式求值（如 `student.name`）                                |
| `eval_condition(cond, ctx)`    | 294 | 条件表达式求值（支持 `==` `!=` `>` `<` `>=` `<=` `and` `or` `not`） |
| `escape_html(text)`            | 341 | HTML 转义                                                  |

---

#### 4.1.2 HTTP 服务

##### 服务器类（第1435-1454行）

| 类 / 函数                | 行号   | 说明                                 |
| --------------------- | ---- | ---------------------------------- |
| `ThreadingHTTPServer` | 1435 | 多线程 HTTP 服务器，`daemon_threads=True` |
| `run_server(port)`    | 1440 | 启动服务，监听 `0.0.0.0:{port}`           |

##### AppHandler 基方法

| 方法                               | 行号  | 说明                                     |
| -------------------------------- | --- | -------------------------------------- |
| `do_GET()`                       | 360 | GET 路由分发（30条规则）                        |
| `do_POST()`                      | 413 | POST 路由分发（27条规则），自动解析表单和 multipart     |
| `serve_static(path)`             | 462 | 提供静态文件，含 `Cache-Control: max-age=3600` |
| `send_html(html)`                | 491 | 发送 HTML 响应                             |
| `send_csv(content, filename)`    | 499 | 发送 CSV 下载                              |
| `send_error_page(msg, back_url)` | 509 | 渲染友好错误页                                |
| `redirect(url)`                  | 517 | 302 重定向                                |
| `render_page(template, **ctx)`   | 523 | 渲染完整页面（自动包裹 header/footer）             |

---

#### 4.1.3 页面路由与处理器

##### 仪表盘

| 方法               | GET POST | URL | 说明                       |
| ---------------- | -------- | --- | ------------------------ |
| `dashboard_page` | GET      | `/` | 首页仪表盘：学员数/班级数/课程数/近期课程提醒 |

##### 学员管理

| 方法                        | GET POST | URL                        | 说明                             |
| ------------------------- | -------- | -------------------------- | ------------------------------ |
| `students_page`           | GET      | `/students`                | 列表（支持搜索/年级/级次/状态筛选 + 分页，每页15条） |
| `student_new_page`        | GET      | `/students/new`            | 新增表单                           |
| `student_show_page`       | GET      | `/students/{id}`           | 详情（含班级、成绩列表、缴费记录）              |
| `student_edit_page`       | GET      | `/students/{id}/edit`      | 编辑表单                           |
| `students_create`         | POST     | `/students`                | 创建学员                           |
| `students_update`         | POST     | `/students/{id}`           | 更新学员                           |
| `students_delete`         | POST     | `/students/{id}/delete`    | 删除学员                           |
| `student_tracking_page`   | GET      | `/students/{id}/tracking`  | 学习追踪：Chart.js 成绩变化折线图 + 均分线    |
| `students_batch_page`     | GET      | `/students/batch`          | 批量操作页（含筛选 + 全选）                |
| `students_batch_action`   | POST     | `/students/batch`          | 执行批量操作（加入班级 / 修改信息）            |
| `students_import_page`    | GET      | `/students/import`         | 批量导入页                          |
| `students_import_preview` | POST     | `/students/import-preview` | 导入预览                           |
| `students_import`         | POST     | `/students/import`         | 执行导入                           |

##### 班级管理

| 方法                      | GET POST | URL                      | 说明               |
| ----------------------- | -------- | ------------------------ | ---------------- |
| `classes_page`          | GET      | `/classes`               | 班级列表             |
| `class_new_page`        | GET      | `/classes/new`           | 新增班级             |
| `class_show_page`       | GET      | `/classes/{id}`          | 班级详情（含学员名单、课程安排） |
| `class_edit_page`       | GET      | `/classes/{id}/edit`     | 编辑班级             |
| `classes_create`        | POST     | `/classes`               | 创建班级             |
| `classes_update`        | POST     | `/classes/{id}`          | 更新班级             |
| `classes_delete`        | POST     | `/classes/{id}/delete`   | 删除班级             |
| `class_students_manage` | POST     | `/classes/{id}/students` | 添加/移除学员（支持按姓名查找） |

##### 课程管理

| 方法                 | GET POST | URL                        | 说明               |
| ------------------ | -------- | -------------------------- | ---------------- |
| `courses_page`     | GET      | `/courses`                 | 课程列表             |
| `course_new_page`  | GET      | `/courses/new`             | 新增课程             |
| `course_show_page` | GET      | `/courses/{id}`            | 课程详情（含出勤签到表）     |
| `course_edit_page` | GET      | `/courses/{id}/edit`       | 编辑课程             |
| `courses_create`   | POST     | `/courses`                 | 创建课程             |
| `courses_update`   | POST     | `/courses/{id}`            | 更新课程             |
| `courses_delete`   | POST     | `/courses/{id}/delete`     | 删除课程             |
| `attendance_save`  | POST     | `/courses/{id}/attendance` | 保存出勤（含线上/线下参与方式） |

##### 成绩管理

| 方法                   | GET POST | URL                   | 说明                          |
| -------------------- | -------- | --------------------- | --------------------------- |
| `grades_page`        | GET      | `/grades`             | 列表（按班级分组展示 + 统计面板 + 成绩分布图）  |
| `grade_new_page`     | GET      | `/grades/new`         | 新增成绩                        |
| `grade_edit_page`    | GET      | `/grades/{id}/edit`   | 编辑成绩                        |
| `grades_create`      | POST     | `/grades`             | 创建成绩                        |
| `grades_update`      | POST     | `/grades/{id}`        | 更新成绩                        |
| `grades_delete`      | POST     | `/grades/{id}/delete` | 删除成绩                        |
| `grades_import_page` | GET      | `/grades/import`      | CSV 导入页（支持表头自动映射）           |
| `grades_import`      | POST     | `/grades/import`      | 执行导入                        |
| `grades_export`      | GET      | `/grades/export`      | 导出 CSV（UTF-8 BOM，Excel 可直开） |

##### 作业管理

| 方法                              | GET POST | URL                               | 说明                  |
| ------------------------------- | -------- | --------------------------------- | ------------------- |
| `assignments_page`              | GET      | `/assignments`                    | 列表（支持按平均分排序 + 均分列）  |
| `assignment_new_page`           | GET      | `/assignments/new`                | 新增作业                |
| `assignment_show_page`          | GET      | `/assignments/{id}`               | 详情（含提交状态/成绩可编辑表格）   |
| `assignment_edit_page`          | GET      | `/assignments/{id}/edit`          | 编辑作业                |
| `assignment_submissions_update` | POST     | `/assignments/{id}/submissions`   | 批量更新状态/成绩           |
| `assignment_import_scores_page` | GET      | `/assignments/{id}/import-scores` | CSV 成绩导入页           |
| `assignment_import_scores`      | POST     | `/assignments/{id}/import-scores` | 执行导入（未导入学员自动标"未提交"） |
| `assignments_create`            | POST     | `/assignments`                    | 创建作业                |
| `assignments_update`            | POST     | `/assignments/{id}`               | 更新作业                |
| `assignments_delete`            | POST     | `/assignments/{id}/delete`        | 删除作业                |

##### 其他模块

| 方法                  | GET POST | URL                     | 说明              |
| ------------------- | -------- | ----------------------- | --------------- |
| `attendances_page`  | GET      | `/attendances`          | 出勤记录列表          |
| `payments_page`     | GET      | `/payments`             | 缴费记录列表（含欠费逾期标记） |
| `payment_new_page`  | GET      | `/payments/new`         | 新增缴费            |
| `payment_edit_page` | GET      | `/payments/{id}/edit`   | 编辑缴费            |
| `payments_create`   | POST     | `/payments`             | 创建缴费            |
| `payments_update`   | POST     | `/payments/{id}`        | 更新缴费            |
| `payments_delete`   | POST     | `/payments/{id}/delete` | 删除缴费            |

##### API 接口

| 方法            | URL             | 说明                       |
| ------------- | --------------- | ------------------------ |
| `api_handler` | `/api/students` | 返回在读学员列表（JSON，含 id/name） |
| `api_handler` | `/api/classes`  | 返回班级列表（JSON）             |

---

### 4.2 database.py — 数据库操作层（~1544行）

#### 4.2.1 基础设施函数

| 函数                                        | 行号  | 说明                          |
| ----------------------------------------- | --- | --------------------------- |
| `_add_column(cursor, table, column, def)` | 26  | 安全添加列（IF NOT EXISTS 模拟）     |
| `migrate_db()`                            | 34  | 数据库迁移：补充旧表缺失字段、填充默认值        |
| `compute_graduation_year(cohort)`         | 74  | 毕业届次计算：26级→29届（cohort+3）    |
| `_to_int(value, default)`                 | 85  | 安全整数转换                      |
| `_to_float(value, default)`               | 95  | 安全浮点数转换                     |
| `get_db()`                                | 105 | 获取连接（启用 WAL、外键、row_factory） |
| `init_db()`                               | 113 | 初始化：建10张表、建10个索引、执行迁移       |
| `row_to_dict(row)`                        | 299 | Row 对象→字典                   |

#### 4.2.2 学员操作（第308-562行）

| 函数                                           | 行号  | 说明                                 |
| -------------------------------------------- | --- | ---------------------------------- |
| `create_student(data)`                       | 308 | INSERT，自动计算 graduation_year        |
| `update_student(id, data)`                   | 329 | UPDATE，重新计算 graduation_year        |
| `get_student(id)`                            | 350 | SELECT BY id                       |
| `find_student_by_name(name)`                 | 359 | SELECT BY name（取最新 cohort）         |
| `get_students(...)`                          | 369 | 多条件 SELECT + LIMIT/OFFSET 分页       |
| `count_students(...)`                        | 401 | SELECT COUNT                       |
| `batch_update_students(ids, fields)`         | 430 | UPDATE ... WHERE id IN (...)       |
| `batch_add_students_to_class(ids, class_id)` | 456 | 批量 INSERT 班级关联                     |
| `batch_import_students(rows)`                | 478 | 批量 INSERT（字典列表）                    |
| `get_distinct_cohorts()`                     | 510 | SELECT DISTINCT cohort             |
| `delete_student(id)`                         | 520 | DELETE CASCADE                     |
| `get_student_classes(id)`                    | 528 | JOIN 获取班级列表                        |
| `get_student_grades(id)`                     | 544 | JOIN 获取成绩（含等级 excellent/pass/fail） |

#### 4.2.3 班级操作（第567-670行）

| 函数                                    | 行号  | 说明                             |
| ------------------------------------- | --- | ------------------------------ |
| `create_class(data)`                  | 567 | INSERT                         |
| `update_class(id, data)`              | 585 | UPDATE                         |
| `get_class(id)`                       | 603 | SELECT BY id                   |
| `get_classes(status)`                 | 612 | SELECT（可选 status 筛选）           |
| `delete_class(id)`                    | 627 | DELETE CASCADE                 |
| `get_class_students(id)`              | 635 | JOIN class_students + students |
| `add_student_to_class(cid, sid)`      | 651 | INSERT INTO class_students     |
| `remove_student_from_class(cid, sid)` | 665 | DELETE FROM class_students     |

#### 4.2.4 课程操作（第673-761行）

| 函数                        | 行号  | 说明                        |
| ------------------------- | --- | ------------------------- |
| `create_course(data)`     | 675 | INSERT（含 mode 上课方式字段）     |
| `update_course(id, data)` | 695 | UPDATE                    |
| `get_course(id)`          | 715 | SELECT + JOIN classes     |
| `get_courses(...)`        | 729 | 多条件 SELECT（class_id/日期范围） |
| `delete_course(id)`       | 756 | DELETE CASCADE            |

#### 4.2.5 出勤操作（第764-792行）

| 函数                                             | 行号  | 说明                                   |
| ---------------------------------------------- | --- | ------------------------------------ |
| `set_attendance(cid, sid, status, note, mode)` | 766 | UPSERT（INSERT ON CONFLICT DO UPDATE） |
| `get_course_attendances(cid)`                  | 781 | SELECT + JOIN students               |

#### 4.2.6 成绩操作（第795-1054行）

| 函数                                          | 行号   | 说明                                   |
| ------------------------------------------- | ---- | ------------------------------------ |
| `create_grade(data)`                        | 797  | INSERT                               |
| `update_grade(id, data)`                    | 818  | UPDATE                               |
| `get_grade(id)`                             | 839  | SELECT BY id                         |
| `get_grades(...)`                           | 848  | 多条件 SELECT（含等级计算和 RANK 窗口函数）         |
| `delete_grade(id)`                          | 881  | DELETE                               |
| `export_grades_to_csv(...)`                 | 889  | 导出为 UTF-8 BOM CSV                    |
| `import_grades_from_csv(content, class_id)` | 904  | 表头自动映射导入（支持 姓名/班级/考试/科目/得分/满分/日期/备注） |
| `get_grade_statistics(...)`                 | 1006 | AVG / MAX / MIN / COUNT              |
| `get_grade_ranking(...)`                    | 1032 | RANK() OVER (ORDER BY score DESC)    |

#### 4.2.7 作业操作（第1057-1376行）

| 函数                                                         | 行号   | 说明                                    |
| ---------------------------------------------------------- | ---- | ------------------------------------- |
| `create_assignment(data)`                                  | 1059 | INSERT                                |
| `update_assignment(id, data)`                              | 1076 | UPDATE                                |
| `get_assignment(id)`                                       | 1092 | SELECT + JOIN classes                 |
| `get_assignments(class_id, status)`                        | 1101 | 多条件 SELECT                            |
| `delete_assignment(id)`                                    | 1124 | DELETE CASCADE                        |
| **作业提交**                                                   |      |                                       |
| `create_assignment_submission(data)`                       | 1134 | INSERT                                |
| `update_assignment_submission(aid, sid, data)`             | 1150 | UPSERT                                |
| `get_assignment_submissions(aid)`                          | 1169 | SELECT + JOIN students                |
| `get_assignment_stats(aid)`                                | 1183 | COUNT / SUM（按状态分组）                    |
| `get_class_assignment_stats(cid)`                          | 1201 | 所有作业提交统计                              |
| `set_assignment_submission(aid, sid, status, score, note)` | 1223 | 单个 UPSERT（含分数和状态）                     |
| `import_assignment_scores(aid, csv)`                       | 1239 | CSV 导入：命中→标记 submitted，未命中→标记 pending |
| `get_student_assignment_scores(sid)`                       | 1327 | 学员所有作业成绩（按 deadline 排序）               |
| `get_assignments_with_sort(class_id, sort_by)`             | 1346 | 支持 `avg_score` 排序（子查询 AVG）            |

#### 4.2.8 缴费操作（第1380-1461行）

| 函数                         | 行号   | 说明                |
| -------------------------- | ---- | ----------------- |
| `create_payment(data)`     | 1380 | INSERT            |
| `update_payment(id, data)` | 1400 | UPDATE            |
| `get_payment(id)`          | 1420 | SELECT BY id      |
| `get_payments(...)`        | 1429 | 多条件 SELECT + JOIN |
| `delete_payment(id)`       | 1456 | DELETE            |

#### 4.2.9 统计分析（第1466-1538行）

| 函数                         | 行号   | 说明                             |
| -------------------------- | ---- | ------------------------------ |
| `get_dashboard_stats()`    | 1466 | 仪表盘：学员数/班级数/课程数/缴费收入/近期缺勤/即将上课 |
| `get_grade_distribution()` | 1512 | 成绩分布：5个分数段 + 百分比               |

---

### 4.3 seed.py — 测试数据生成（~217行）

| 数据类型 | 数量  | 说明                                   |
| ---- | --- | ------------------------------------ |
| 班级   | 3   | 新高一物理理优班(26级)、高二升高三(25级)、高一提高班(26级)  |
| 学员   | 35  | 8姓氏×10名字随机组合，年级均匀分布，6所合肥中学随机         |
| 班级分配 | 22  | 班级1:10人、班级2:4人、班级3:8人                |
| 课程   | 15  | 运动学到近代物理，前3节已结课，随机线下/线上/同步           |
| 成绩   | 100 | 20学员×5考试，分数 45-100 随机，5个考试名称         |
| 作业   | 4   | 按班级分配，截止日期依次递延7天                     |
| 缴费   | 25  | 金额随机(3000/4500/6000/8000)，类型随机，含欠费逾期 |

### 4.4 student-system.spec — PyInstaller 配置

```python
# 入口脚本
a = Analysis(['app.py'], datas=[
    ('templates', 'templates'),   # 模板文件打包进可执行文件
    ('static', 'static'),         # 静态资源打包进可执行文件
    ('data', 'data'),             # 初始数据目录
])
# 输出：dist/EduFlow
```

运行时：模板/静态从 `_MEIPASS`（临时解压目录）读取，数据库从可执行文件同级 `data/` 目录读写。

### 4.5 templates/ — 模板文件体系

#### 数据流

```
浏览器请求 → do_GET() 路由匹配 → Handler 方法
  → database 查询 → render_page(template, **context)
  → render_template() → 模板引擎解析 → HTML
  → send_html() → 浏览器
```

#### 公共组件

| 文件                     | 内容                                                                                              |
| ---------------------- | ----------------------------------------------------------------------------------------------- |
| `partials/header.html` | `<!DOCTYPE html>` ~ `<body>`，含：SEO meta、CSS/JS 引用、15 个 SVG 图标 symbol、侧边栏导航（8 个菜单项）、主题切换按钮、移动端菜单 |
| `partials/footer.html` | `</main></div></body></html>`                                                                   |
| `partials/error.html`  | 错误提示页：显示 message + 返回链接                                                                         |

#### 模块模板统计

| 模块 | 文件数 | 包含页面                           |
| -- | --- | ------------------------------ |
| 学员 | 7   | 列表、表单、详情、批量操作、批量导入、导入结果、学习追踪   |
| 班级 | 3   | 列表、表单、详情                       |
| 课程 | 3   | 列表、表单、详情（含出勤签到）                |
| 成绩 | 4   | 列表（分组+图表）、表单、导入、导入结果           |
| 作业 | 5   | 列表（含排序）、表单、详情（可编辑状态）、成绩导入、导入结果 |
| 出勤 | 1   | 记录列表                           |
| 缴费 | 2   | 列表、表单                          |

### 4.6 static/ — 静态资源

#### CSS 主要章节（`style.css`，795行）

| 行号      | 章节                            | 说明                                       |
| ------- | ----------------------------- | ---------------------------------------- |
| 1-30    | `:root`                       | 23 个 CSS 变量（颜色/阴影/圆角/过渡）                 |
| 32-57   | `[data-theme="dark"]`         | 深色主题变量覆盖                                 |
| 82-126  | `.sidebar` 系列                 | 260px 固定侧边栏，Logo 渐变图标                    |
| 128-172 | `.nav-item` 系列                | 导航菜单 active 渐变高亮                         |
| 246-324 | `.stat-card` 系列               | 统计卡片（5 色图标 + 玻璃拟态）                       |
| 326-381 | `.data-table`                 | 数据表格（斑马纹 + hover 效果）                     |
| 383-398 | `.badge` 系列                   | 6 色徽章（green/blue/red/orange/gray/purple） |
| 400-456 | `.btn` 系列                     | 按钮系统（primary/secondary/danger/sm）        |
| 458-517 | `.form-*` 系列                  | 表单组件（focus 高亮 + 错误状态）                    |
| 519-545 | `.filter-bar` / `.search-box` | 搜索筛选组件                                   |
| 547-571 | `.pagination`                 | 分页组件                                     |
| 594-629 | `.detail-*` 系列                | 详情页双栏网格                                  |
| 692-740 | `@media` queries              | 1024px 断点响应式 + 移动端菜单                     |
| 742-761 | `.toast`                      | Toast 通知（底部 fixed 弹出）                    |

#### JS 函数列表（`app.js`，118行）

| 函数                                    | 说明                                   |
| ------------------------------------- | ------------------------------------ |
| `initTheme()`                         | 从 localStorage 读取主题并应用               |
| `setTheme(theme)`                     | 设置 `data-theme` 属性 + 写入 localStorage |
| `toggleTheme(theme)`                  | 按钮点击切换主题                             |
| `toggleMobileMenu()`                  | 移动端菜单开合                              |
| `confirmDelete(msg)`                  | 删除确认弹窗                               |
| `showToast(msg, type)`                | 3 秒 Toast 提示                         |
| `exportTableToCSV(tableId, filename)` | 表格→CSV 下载（含 BOM）                     |

全局初始化（DOMContentLoaded）：

- 主题按钮事件绑定
- `prefers-color-scheme` 系统主题监听
- 删除表单 `data-confirm` 拦截
- 表格行 `[data-href]` 点击跳转

---

## 5. 数据架构

### 5.1 数据库表结构

#### students（学员表）

| 字段              | 类型      | 约束                        | 说明                  |
| --------------- | ------- | ------------------------- | ------------------- |
| id              | INTEGER | PK AUTOINCREMENT          | 主键                  |
| name            | TEXT    | NOT NULL                  | 姓名                  |
| phone           | TEXT    |                           | 联系电话                |
| wechat          | TEXT    |                           | 微信号                 |
| school          | TEXT    |                           | 就读学校                |
| cohort          | TEXT    |                           | 级次（如 26）            |
| grade           | TEXT    |                           | 当前年级（高一/高二/高三）      |
| graduation_year | TEXT    |                           | 毕业届次（自动计算，如 29）     |
| parent_name     | TEXT    |                           | 家长姓名                |
| parent_phone    | TEXT    |                           | 家长电话                |
| address         | TEXT    |                           | 家庭地址                |
| status          | TEXT    | DEFAULT 'active'          | 状态（active/inactive） |
| note            | TEXT    |                           | 备注                  |
| created_at      | TEXT    | DEFAULT CURRENT_TIMESTAMP | 创建时间                |
| updated_at      | TEXT    | DEFAULT CURRENT_TIMESTAMP | 更新时间                |

**索引**：name, cohort, status

#### classes（班级表）

| 字段           | 类型      | 约束                        | 说明   |
| ------------ | ------- | ------------------------- | ---- |
| id           | INTEGER | PK AUTOINCREMENT          | 主键   |
| name         | TEXT    | NOT NULL                  | 班级名称 |
| cohort       | TEXT    |                           | 级次   |
| grade        | TEXT    |                           | 年级   |
| subject      | TEXT    |                           | 科目   |
| max_students | INTEGER |                           | 人数上限 |
| teacher_name | TEXT    |                           | 授课教师 |
| status       | TEXT    | DEFAULT 'active'          | 状态   |
| description  | TEXT    |                           | 描述   |
| created_at   | TEXT    | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

#### class_students（班级-学员关联表）

| 字段         | 类型      | 约束                        | 说明   |
| ---------- | ------- | ------------------------- | ---- |
| id         | INTEGER | PK AUTOINCREMENT          | 主键   |
| class_id   | INTEGER | FK → classes.id           | 班级ID |
| student_id | INTEGER | FK → students.id          | 学员ID |
| join_date  | TEXT    | DEFAULT CURRENT_TIMESTAMP | 加入时间 |

**约束**：UNIQUE(class_id, student_id)

#### courses（课程表）

| 字段           | 类型      | 约束                        | 说明                              |
| ------------ | ------- | ------------------------- | ------------------------------- |
| id           | INTEGER | PK AUTOINCREMENT          | 主键                              |
| class_id     | INTEGER | FK → classes.id CASCADE   | 所属班级                            |
| title        | TEXT    | NOT NULL                  | 课程标题                            |
| scheduled_at | TEXT    |                           | 上课时间（ISO 8601）                  |
| duration     | INTEGER |                           | 时长（分钟）                          |
| location     | TEXT    |                           | 上课地点/会议链接                       |
| mode         | TEXT    | DEFAULT 'offline'         | 上课方式（offline/online/hybrid）     |
| status       | TEXT    | DEFAULT 'planned'         | 状态（planned/completed/cancelled） |
| description  | TEXT    |                           | 描述                              |
| created_at   | TEXT    | DEFAULT CURRENT_TIMESTAMP | 创建时间                            |

#### course_attendances（出勤表）

| 字段         | 类型      | 约束                        | 说明                                   |
| ---------- | ------- | ------------------------- | ------------------------------------ |
| id         | INTEGER | PK AUTOINCREMENT          | 主键                                   |
| course_id  | INTEGER | FK → courses.id CASCADE   | 课程ID                                 |
| student_id | INTEGER | FK → students.id CASCADE  | 学员ID                                 |
| status     | TEXT    | DEFAULT 'present'         | 状态（present/absent/late/leave/online） |
| mode       | TEXT    |                           | 参与方式（offline/online）                 |
| note       | TEXT    |                           | 备注                                   |
| created_at | TEXT    | DEFAULT CURRENT_TIMESTAMP | 创建时间                                 |

**约束**：UNIQUE(course_id, student_id)

#### grades（成绩表）

| 字段         | 类型      | 约束                        | 说明   |
| ---------- | ------- | ------------------------- | ---- |
| id         | INTEGER | PK AUTOINCREMENT          | 主键   |
| student_id | INTEGER | FK → students.id CASCADE  | 学员ID |
| class_id   | INTEGER | FK → classes.id           | 班级ID |
| exam_name  | TEXT    | NOT NULL                  | 考试名称 |
| subject    | TEXT    |                           | 科目   |
| score      | REAL    |                           | 得分   |
| max_score  | REAL    | DEFAULT 100               | 满分   |
| exam_date  | TEXT    |                           | 考试日期 |
| note       | TEXT    |                           | 备注   |
| created_at | TEXT    | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**索引**：student_id, class_id, exam_name

#### assignments（作业表）

| 字段         | 类型      | 约束                        | 说明                   |
| ---------- | ------- | ------------------------- | -------------------- |
| id         | INTEGER | PK AUTOINCREMENT          | 主键                   |
| class_id   | INTEGER | FK → classes.id           | 所属班级                 |
| title      | TEXT    | NOT NULL                  | 作业标题                 |
| content    | TEXT    |                           | 作业内容                 |
| deadline   | TEXT    |                           | 截止日期                 |
| status     | TEXT    | DEFAULT 'active'          | 状态（active/completed） |
| created_at | TEXT    | DEFAULT CURRENT_TIMESTAMP | 创建时间                 |

#### assignment_submissions（作业提交表）

| 字段            | 类型      | 约束                          | 说明                         |
| ------------- | ------- | --------------------------- | -------------------------- |
| id            | INTEGER | PK AUTOINCREMENT            | 主键                         |
| assignment_id | INTEGER | FK → assignments.id CASCADE | 作业ID                       |
| student_id    | INTEGER | FK → students.id CASCADE    | 学员ID                       |
| status        | TEXT    | DEFAULT 'submitted'         | 状态（submitted/late/pending） |
| score         | REAL    |                             | 得分                         |
| submitted_at  | TEXT    |                             | 提交时间                       |
| note          | TEXT    |                             | 备注                         |

**约束**：UNIQUE(assignment_id, student_id)

#### payments（缴费表）

| 字段         | 类型      | 约束                        | 说明                         |
| ---------- | ------- | ------------------------- | -------------------------- |
| id         | INTEGER | PK AUTOINCREMENT          | 主键                         |
| student_id | INTEGER | FK → students.id CASCADE  | 学员ID                       |
| class_id   | INTEGER | FK → classes.id           | 班级ID                       |
| amount     | REAL    |                           | 金额                         |
| type       | TEXT    | DEFAULT 'tuition'         | 类型（tuition/material/other） |
| status     | TEXT    | DEFAULT 'paid'            | 状态（paid/unpaid/overdue）    |
| paid_at    | TEXT    |                           | 缴费日期                       |
| due_date   | TEXT    |                           | 截止日期                       |
| note       | TEXT    |                           | 备注                         |
| created_at | TEXT    | DEFAULT CURRENT_TIMESTAMP | 创建时间                       |

### 5.2 表关系

```
students ──┬── class_students ── classes
           ├── course_attendances ── courses
           ├── grades ── classes
           ├── assignment_submissions ── assignments ── classes
           └── payments ── classes
```

---

## 6. 自定义模板引擎参考

### 支持语法

| 语法      | 示例                                                  | 说明                       |
| ------- | --------------------------------------------------- | ------------------------ |
| 变量      | `{{ name }}`                                        | 输出变量值（已自动 HTML 转义）       |
| 点号访问    | `{{ student.name }}`                                | 访问字典/对象属性                |
| 默认值     | `{{ name\|default:'--' }}`                          | 值为空时显示默认值                |
| 长度      | `{{ list\|length }}`                                | 返回列表长度                   |
| if/else | `{% if x == 'active' %}...{% else %}...{% endif %}` | 条件判断（支持 == != > < >= <=） |
| elif    | `{% elif x == 'inactive' %}`                        | 多分支                      |
| and/or  | `{% if a and b %}`                                  | 逻辑与/或                    |
| not     | `{% if not empty %}`                                | 逻辑非                      |
| for/in  | `{% for item in items %}...{% endfor %}`            | 循环遍历                     |
| include | `{% include "partials/header.html" %}`              | 包含子模板                    |

### 限制

- **不支持算术运算**：`{{ page + 1 }}` 无效，需在 Handler 中预先计算（如 `next_page = page + 1`）再传入模板
- **不支持方法调用**：`{{ dict.items() }}` 无效，需在 Handler 中预处理数据结构
- **不支持方括号索引**：`{{ map[key] }}` 无效，需用点号 `{{ student.att.status }}` 或将数据扁平化
- **不支持 `{% elif %}`**：需用连续的 `{% if %}` 替代

---

## 7. 功能模块速查表

| 模块  | 列表 URL         | 新增 URL             | 详情 URL              | 特色功能                  |
| --- | -------------- | ------------------ | ------------------- | --------------------- |
| 仪表盘 | `/`            | -                  | -                   | 统计卡片 + 近期课程           |
| 学员  | `/students`    | `/students/new`    | `/students/{id}`    | 搜索/分页/CSV导入/批量操作/学习追踪 |
| 班级  | `/classes`     | `/classes/new`     | `/classes/{id}`     | 学员管理/课程关联             |
| 课程  | `/courses`     | `/courses/new`     | `/courses/{id}`     | 线上/线下/同步 + 出勤签到       |
| 成绩  | `/grades`      | `/grades/new`      | -                   | 按班级分组/分布图/CSV导入导出     |
| 作业  | `/assignments` | `/assignments/new` | `/assignments/{id}` | 状态编辑/成绩导入/按均分排序       |
| 出勤  | `/attendances` | -                  | -                   | 按班级筛选                 |
| 缴费  | `/payments`    | `/payments/new`    | -                   | 欠费逾期标记                |

---

## 8. 常见修改指南

### 添加新页面（3 步）

1. **创建模板** 在 `templates/` 下新建 HTML 文件，使用 `{% include "partials/header.html" %}` 和 `{% include "partials/footer.html" %}`
2. **添加路由** 在 `app.py` 的 `do_GET()` 路由列表中添加 `(r'^/your/path$', self.your_handler)`
3. **添加 Handler** 在 `AppHandler` 类中添加方法，调用 `self.render_page(...)` 渲染

```python
def your_page(self, method, match, query):
    data = db.some_query()
    self.render_page('your/template.html',
                    active_menu='your_menu',
                    data=data,
                    title='页面标题')
```

### 添加新数据库表（2 步）

1. **在 `init_db()` 中添加 CREATE TABLE 语句**
2. **添加 CRUD 函数**（参考现有函数的命名和模式）

```python
# 创建
def create_xxx(data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO xxx (...) VALUES (...)')
    conn.commit()
    return cursor.lastrowid

# 查询
def get_xxx(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM xxx WHERE id = ?', (id,))
    return row_to_dict(cursor.fetchone())
```

### 修改主题配色

在 `static/css/style.css` 的 `:root` 块中修改 CSS 变量：

```css
:root {
    --primary-color: #3b82f6;      /* 主题色 */
    --success-color: #22c55e;      /* 成功/在读 */
    --danger-color: #ef4444;       /* 危险/删除 */
    --bg-primary: #ffffff;         /* 主背景 */
    --bg-secondary: #f9fafb;       /* 次背景 */
    /* ... 更多变量见 CSS 第 1-30 行 */
}
```

### 打包发布

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller student-system.spec --clean

# 输出目录
ls dist/
# → EduFlow
# → data/database.sqlite
```

---

## 9. 注意事项与已知限制

| 项目             | 说明                                                       |
| -------------- | -------------------------------------------------------- |
| **模板引擎限制**     | 不支持算术表达式、方法调用、方括号索引，需在 Handler 中预处理                      |
| **模板缓存**       | 基于文件修改时间（mtime），修改模板后自动刷新，无需重启                           |
| **数据库迁移**      | `migrate_db()` 在 `init_db()` 中自动执行，新增字段自动补充默认值           |
| **macOS 首次运行** | 打包程序可能提示"无法验证开发者"，右键打开或 `xattr -dr com.apple.quarantine` |
| **并发能力**       | 多线程服务器，常规使用场景（2-5 并发）无压力                                 |
| **端口占用**       | 默认 3000 端口，修改 `run_server(port)` 参数即可                    |
| **数据备份**       | 直接复制 `data/database.sqlite` 文件                           |
| **浏览器兼容**      | 推荐 Chrome/Firefox/Safari 最新版，Chart.js 需联网加载 CDN          |

---

> 项目作者：李老师 | 技术支持：Senior Developer | 最后更新：2026-07-08
