"""
app.py - 学员管理系统主入口
使用 Python 标准库 http.server + sqlite3，无需任何外部依赖
"""

import os
import sys
import json
import re
import csv
import io
import urllib.parse
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import HTTPStatus
from socketserver import ThreadingMixIn
from datetime import datetime

# 判断运行环境：PyInstaller 打包后资源在 _MEIPASS，数据文件放在可执行文件目录
if getattr(sys, 'frozen', False):
    ASSETS_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    DATA_DIR = os.path.dirname(sys.executable)
else:
    ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = ASSETS_DIR

# 让数据库层知道数据目录位置
os.environ['STUDENT_SYSTEM_DATA_DIR'] = DATA_DIR

# 记录数据库是否已存在（在 init_db 创建之前检查）
DB_PATH = os.path.join(DATA_DIR, 'data', 'database.sqlite')
DB_EXISTED = os.path.exists(DB_PATH)

import database as db

# 初始化数据库
db.init_db()

TEMPLATES_DIR = os.path.join(ASSETS_DIR, 'templates')
STATIC_DIR = os.path.join(ASSETS_DIR, 'static')


# ===== 模板引擎 =====
# 使用 AST 解析，完整支持 if/elif/else、for、include 嵌套

_TEMPLATE_CACHE = {}


class TextNode:
    def __init__(self, text):
        self.text = text

    def render(self, context):
        return self.text


class VarNode:
    def __init__(self, expr, default='', filters=None):
        self.expr = expr
        self.default = default
        self.filters = filters or []

    def render(self, context):
        value = get_value(self.expr, context)
        if value is None or value == '':
            value = self.default
        for f in self.filters:
            if f == 'length':
                try:
                    value = len(value)
                except TypeError:
                    value = 0
        if value is None:
            return ''
        return escape_html(str(value))


class IfNode:
    def __init__(self, branches, else_nodes):
        self.branches = branches  # [(condition_expr, nodes)]
        self.else_nodes = else_nodes

    def render(self, context):
        for cond, nodes in self.branches:
            if eval_condition(cond, context):
                return evaluate_nodes(nodes, context)
        return evaluate_nodes(self.else_nodes, context)


class ForNode:
    def __init__(self, var_name, list_expr, nodes):
        self.var_name = var_name
        self.list_expr = list_expr
        self.nodes = nodes

    def render(self, context):
        items = get_value(self.list_expr, context)
        if not items:
            return ''
        result = []
        for item in items:
            ctx = context.copy()
            ctx[self.var_name] = item
            # 暴露 forloop 相关变量
            ctx['forloop'] = {'parentloop': context.get('forloop', {})}
            result.append(evaluate_nodes(self.nodes, ctx))
        return ''.join(result)


class IncludeNode:
    def __init__(self, template_name):
        self.template_name = template_name

    def render(self, context):
        return render_template(self.template_name, **context)


def tokenize(content):
    """将模板内容切分为文本和标签 token"""
    tokens = []
    pos = 0
    pattern = re.compile(r'{%.*?%}|{{.*?}}', re.DOTALL)
    for match in pattern.finditer(content):
        if match.start() > pos:
            tokens.append(('text', content[pos:match.start()]))
        tag = match.group(0)
        if tag.startswith('{%'):
            inner = tag[2:-2].strip()
            tokens.append(('tag', inner))
        else:
            inner = tag[2:-2].strip()
            tokens.append(('var', inner))
        pos = match.end()
    if pos < len(content):
        tokens.append(('text', content[pos:]))
    return tokens


def parse_var(expr):
    """解析 {{ variable|default:'xxx' }} 及 |length 过滤器"""
    parts = [p.strip() for p in expr.split('|')]
    var_name = parts[0]
    filters = []
    default = ''
    for p in parts[1:]:
        if p.startswith('default:'):
            default = p[8:].strip().strip('"\'')
        elif p == 'length':
            filters.append('length')
    return VarNode(var_name, default=default, filters=filters)


def parse_if(tokens, start_i):
    """解析 if/elif/else/endif 块，返回 (node, next_i)"""
    cond = tokens[start_i][1].split(None, 1)[1].strip()
    branches = [(cond, [])]
    i = start_i + 1
    current = 0

    while i < len(tokens):
        tok_type, tok_val = tokens[i]
        if tok_type == 'tag':
            parts = tok_val.split(None, 1)
            tag_name = parts[0]
            if tag_name == 'elif':
                cond = parts[1].strip() if len(parts) > 1 else ''
                branches.append((cond, []))
                current += 1
                i += 1
                continue
            elif tag_name == 'else':
                i += 1
                nodes, i = parse_nodes(tokens, i, end_tags={'endif'})
                if i < len(tokens) and tokens[i][1].split(None, 1)[0] == 'endif':
                    i += 1
                return IfNode(branches, nodes), i
            elif tag_name == 'endif':
                i += 1
                return IfNode(branches, []), i
        # 普通节点加入当前分支
        node, i = parse_token(tokens, i)
        if node is not None:
            branches[current][1].append(node)

    return IfNode(branches, []), i


def parse_for(tokens, start_i):
    """解析 for 循环，返回 (node, next_i)"""
    parts = tokens[start_i][1].split()
    if len(parts) < 4 or parts[2] != 'in':
        return TextNode(''), start_i + 1
    var_name = parts[1]
    list_expr = parts[3]
    i = start_i + 1
    nodes, i = parse_nodes(tokens, i, end_tags={'endfor'})
    if i < len(tokens) and tokens[i][1].split(None, 1)[0] == 'endfor':
        i += 1
    return ForNode(var_name, list_expr, nodes), i


def parse_include(tok_val):
    """解析 include 标签 {% include "name.html" %}"""
    match = re.match(r'include\s+"([^"]+)"', tok_val)
    if match:
        return match.group(1)
    parts = tok_val.split(None, 1)
    name = parts[1].strip().strip('"\'') if len(parts) > 1 else ''
    return name


def parse_token(tokens, i):
    """解析单个 token，返回 (node, next_i)"""
    if i >= len(tokens):
        return None, i
    tok_type, tok_val = tokens[i]
    if tok_type == 'text':
        return TextNode(tok_val), i + 1
    elif tok_type == 'var':
        return parse_var(tok_val), i + 1
    elif tok_type == 'tag':
        parts = tok_val.split(None, 1)
        tag_name = parts[0]
        if tag_name == 'if':
            return parse_if(tokens, i)
        elif tag_name == 'for':
            return parse_for(tokens, i)
        elif tag_name == 'include':
            return IncludeNode(parse_include(tok_val)), i + 1
        else:
            # 未识别的标签按文本输出（便于调试）
            return TextNode('{% ' + tok_val + ' %}'), i + 1
    return None, i + 1


def parse_nodes(tokens, start_i, end_tags=None):
    """顺序解析节点，直到遇到 end_tags 中的标签"""
    nodes = []
    i = start_i
    while i < len(tokens):
        tok_type, tok_val = tokens[i]
        if tok_type == 'tag':
            tag_name = tok_val.split(None, 1)[0]
            if end_tags and tag_name in end_tags:
                return nodes, i
        node, i = parse_token(tokens, i)
        if node is not None:
            nodes.append(node)
    return nodes, i


def evaluate_nodes(nodes, context):
    """计算节点列表"""
    return ''.join(node.render(context) for node in nodes)


def render_template(template_name, **context):
    """渲染模板：完整支持 if/elif/else、for、include 和变量"""
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(template_path):
        return f"<!-- Template not found: {template_name} -->"

    cache_key = (template_path, os.path.getmtime(template_path))
    cached = _TEMPLATE_CACHE.get(template_path)
    if cached and cached[0] == cache_key:
        nodes = cached[1]
    else:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        tokens = tokenize(content)
        nodes, _ = parse_nodes(tokens, 0)
        _TEMPLATE_CACHE[template_path] = (cache_key, nodes)

    return evaluate_nodes(nodes, context)


def get_value(expr, context):
    """获取表达式值，支持点号访问、整数索引和简单过滤"""
    expr = expr.strip()
    if not expr:
        return ''
    parts = expr.split('.')
    value = context.get(parts[0].strip(), '')
    for part in parts[1:]:
        if value is None:
            return ''
        part = part.strip()
        if isinstance(value, dict):
            value = value.get(part)
        elif hasattr(value, part):
            value = getattr(value, part)
        else:
            value = ''
    if value is None:
        return ''
    return value


def eval_condition(cond, context):
    """计算条件表达式"""
    cond = cond.strip()
    if not cond:
        return False

    # 支持 not
    if cond.startswith('not ') and len(cond) > 4:
        return not eval_condition(cond[4:], context)

    # 支持 and / or（简单实现）
    if ' and ' in cond:
        return all(eval_condition(c.strip(), context) for c in cond.split(' and ', 1))
    if ' or ' in cond:
        return any(eval_condition(c.strip(), context) for c in cond.split(' or ', 1))

    # 比较运算符（注意顺序：先匹配双字符）
    for op in ['==', '!=', '>=', '<=', '>', '<']:
        if op in cond:
            parts = cond.split(op, 1)
            left = parts[0].strip()
            right = parts[1].strip()
            # 去除字符串引号
            if (right.startswith('"') and right.endswith('"')) or \
               (right.startswith("'") and right.endswith("'")):
                right = right[1:-1]
            lv = get_value(left, context)
            rv = get_value(right, context) if right in context or '.' in right else right

            if op == '==':
                return str(lv) == str(rv)
            if op == '!=':
                return str(lv) != str(rv)
            try:
                lv_n = float(lv) if lv != '' else 0
                rv_n = float(rv) if rv != '' else 0
                if op == '>=': return lv_n >= rv_n
                if op == '<=': return lv_n <= rv_n
                if op == '>': return lv_n > rv_n
                if op == '<': return lv_n < rv_n
            except (ValueError, TypeError):
                return False

    # 简单真值判断
    return bool(get_value(cond, context))


def escape_html(text):
    """HTML 转义"""
    if text is None:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#x27;'))


class AppHandler(BaseHTTPRequestHandler):
    """自定义 HTTP 请求处理器"""
    
    def log_message(self, format, *args):
        """静默日志，减少输出干扰"""
        pass
    
    @staticmethod
    def _safe_int(value, default=0):
        """安全整数转换，非数字返回默认值（防 500）"""
        if value is None or value == '':
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        # 静态文件
        if path.startswith('/static/'):
            self.serve_static(path)
            return
        
        # 页面路由
        routes = [
            (r'^/$', self.dashboard_page),
            (r'^/students$', self.students_page),
            (r'^/students/new$', self.student_new_page),
            (r'^/students/batch$', self.students_batch_page),
            (r'^/students/import$', self.students_import_page),
            (r'^/students/(\d+)$', self.student_show_page),
            (r'^/students/(\d+)/edit$', self.student_edit_page),
            (r'^/classes$', self.classes_page),
            (r'^/classes/new$', self.class_new_page),
            (r'^/classes/(\d+)$', self.class_show_page),
            (r'^/classes/(\d+)/edit$', self.class_edit_page),
            (r'^/courses$', self.courses_page),
            (r'^/courses/new$', self.course_new_page),
            (r'^/courses/(\d+)$', self.course_show_page),
            (r'^/courses/(\d+)/edit$', self.course_edit_page),
            (r'^/grades$', self.grades_page),
            (r'^/grades/new$', self.grade_new_page),
            (r'^/grades/export$', self.grades_export),
            (r'^/grades/import$', self.grades_import_page),
            (r'^/grades/(\d+)/edit$', self.grade_edit_page),
            (r'^/assignments$', self.assignments_page),
            (r'^/assignments/new$', self.assignment_new_page),
            (r'^/assignments/(\d+)$', self.assignment_show_page),
            (r'^/assignments/(\d+)/edit$', self.assignment_edit_page),
            (r'^/assignments/(\d+)/import-scores$', self.assignment_import_scores_page),
            (r'^/students/(\d+)/tracking$', self.student_tracking_page),
            (r'^/attendances$', self.attendances_page),
            (r'^/payments$', self.payments_page),
            (r'^/payments/new$', self.payment_new_page),
            (r'^/payments/(\d+)/edit$', self.payment_edit_page),
            (r'^/rank-compare$', self.rank_compare_page),
            (r'^/api/.*', self.api_handler),
        ]
        
        for pattern, handler in routes:
            match = re.match(pattern, path)
            if match:
                handler('GET', match, query)
                return
        
        self.send_error(404)
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        # 读取表单数据
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        form_data = urllib.parse.parse_qs(post_data)
        # 转换为单值字典
        data = {k: v[0] if len(v) == 1 else v for k, v in form_data.items()}
        
        routes = [
            (r'^/students$', self.students_create),
            (r'^/students/(\d+)$', self.students_update),
            (r'^/students/(\d+)/delete$', self.students_delete),
            (r'^/students/batch$', self.students_batch_action),
            (r'^/students/import-preview$', self.students_import_preview),
            (r'^/students/import$', self.students_import),
            (r'^/classes$', self.classes_create),
            (r'^/classes/(\d+)$', self.classes_update),
            (r'^/classes/(\d+)/delete$', self.classes_delete),
            (r'^/classes/(\d+)/students$', self.class_students_manage),
            (r'^/courses$', self.courses_create),
            (r'^/courses/(\d+)$', self.courses_update),
            (r'^/courses/(\d+)/delete$', self.courses_delete),
            (r'^/courses/(\d+)/attendance$', self.attendance_save),
            (r'^/grades$', self.grades_create),
            (r'^/grades/(\d+)$', self.grades_update),
            (r'^/grades/(\d+)/delete$', self.grades_delete),
            (r'^/grades/import$', self.grades_import),
            (r'^/assignments$', self.assignments_create),
            (r'^/assignments/(\d+)$', self.assignments_update),
            (r'^/assignments/(\d+)/delete$', self.assignments_delete),
            (r'^/assignments/(\d+)/submissions$', self.assignment_submissions_update),
            (r'^/assignments/(\d+)/import-scores$', self.assignment_import_scores),
            (r'^/payments$', self.payments_create),
            (r'^/payments/(\d+)$', self.payments_update),
            (r'^/payments/(\d+)/delete$', self.payments_delete),
            (r'^/rank-compare$', self.rank_compare_analyze),
        ]
        
        for pattern, handler in routes:
            match = re.match(pattern, path)
            if match:
                handler('POST', match, data)
                return
        
        self.send_error(404)
    
    def serve_static(self, path):
        """提供静态文件，严格限定在 STATIC_DIR 内，防路径穿越"""
        # 剥离 /static/ 前缀
        rel = path
        for prefix in ('/static/', 'static/'):
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                break
        # 归一化 + containment 校验
        file_path = os.path.realpath(os.path.join(STATIC_DIR, rel.lstrip('/')))
        static_root = os.path.realpath(STATIC_DIR)
        if not file_path.startswith(static_root + os.sep) or not os.path.isfile(file_path):
            self.send_error(404)
            return
        
        content_type = 'text/plain'
        if file_path.endswith('.css'):
            content_type = 'text/css'
        elif file_path.endswith('.js'):
            content_type = 'application/javascript'
        elif file_path.endswith('.png'):
            content_type = 'image/png'
        elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif file_path.endswith('.svg'):
            content_type = 'image/svg+xml'
        
        with open(file_path, 'rb') as f:
            content = f.read()
        
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(content))
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.end_headers()
        self.wfile.write(content)
    
    def send_html(self, html, status=200):
        """发送 HTML 响应"""
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(html.encode('utf-8')))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def send_csv(self, content, filename):
        """发送 CSV 文件下载"""
        encoded = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def send_error_page(self, message, back_url='/', status=400):
        """渲染错误提示页"""
        html = render_template('partials/error.html',
                               message=message,
                               back_url=back_url,
                               title='操作失败')
        self.send_html(html, status)

    def redirect(self, url):
        """重定向"""
        self.send_response(302)
        self.send_header('Location', url)
        self.end_headers()
    
    def render_page(self, template, **context):
        """渲染完整页面"""
        # 添加公共上下文
        context['active_menu'] = context.get('active_menu', '')
        html = render_template(template, **context)
        self.send_html(html)
    
    # ===== 仪表盘 =====
    
    def dashboard_page(self, method, match, query):
        stats = db.get_dashboard_stats()
        self.render_page('index.html',
                        active_menu='dashboard',
                        stats=stats,
                        title='仪表盘')
    
    # ===== 学员管理 =====
    
    def students_page(self, method, match, query):
        search = query.get('search', [''])[0]
        grade = query.get('grade', [''])[0]
        cohort = query.get('cohort', [''])[0]
        status = query.get('status', [''])[0]
        page = self._safe_int(query.get('page', ['1'])[0], default=1)
        per_page = 15
        offset = (page - 1) * per_page
        
        students = db.get_students(search=search, grade=grade, cohort=cohort, status=status, limit=per_page, offset=offset)
        total = db.count_students(search=search, grade=grade, cohort=cohort, status=status)
        total_pages = max(1, (total + per_page - 1) // per_page)
        cohorts = db.get_distinct_cohorts()
        
        self.render_page('students/index.html',
                        active_menu='students',
                        students=students,
                        search=search,
                        grade=grade,
                        cohort=cohort,
                        cohorts=cohorts,
                        status=status,
                        page=page,
                        prev_page=page - 1,
                        next_page=page + 1,
                        total_pages=total_pages,
                        total=total,
                        title='学员管理')
    
    def student_new_page(self, method, match, query):
        self.render_page('students/form.html',
                        active_menu='students',
                        student={},
                        title='新增学员')
    
    def student_show_page(self, method, match, query):
        student_id = int(match.group(1))
        student = db.get_student(student_id)
        if not student:
            self.send_error(404)
            return
        
        classes = db.get_student_classes(student_id)
        grades = db.get_student_grades(student_id)
        payments = db.get_payments(student_id=student_id)
        
        self.render_page('students/show.html',
                        active_menu='students',
                        student=student,
                        classes=classes,
                        grades=grades,
                        payments=payments,
                        title=f'学员详情 - {student["name"]}')
    
    def student_edit_page(self, method, match, query):
        student_id = int(match.group(1))
        student = db.get_student(student_id)
        if not student:
            self.send_error(404)
            return
        
        self.render_page('students/form.html',
                        active_menu='students',
                        student=student,
                        title='编辑学员')
    
    def students_create(self, method, match, data):
        if not data.get('name', '').strip():
            self.send_error_page('学员姓名不能为空', back_url='/students/new')
            return
        try:
            db.create_student(data)
            self.redirect('/students')
        except Exception as e:
            self.send_error_page(f'添加失败：{e}', back_url='/students/new')
    
    def students_update(self, method, match, data):
        student_id = int(match.group(1))
        if not data.get('name', '').strip():
            self.send_error_page('学员姓名不能为空', back_url=f'/students/{student_id}/edit')
            return
        try:
            db.update_student(student_id, data)
            self.redirect(f'/students/{student_id}')
        except Exception as e:
            self.send_error_page(f'保存失败：{e}', back_url=f'/students/{student_id}/edit')
    
    def students_delete(self, method, match, data):
        student_id = int(match.group(1))
        db.delete_student(student_id)
        self.redirect('/students')
    
    def student_tracking_page(self, method, match, query):
        """学习追踪：成绩变化图表"""
        student_id = int(match.group(1))
        student = db.get_student(student_id)
        if not student:
            self.send_error(404)
            return
        
        scores = db.get_student_assignment_scores(student_id)
        # 格式化图表数据
        chart_data = []
        total = 0
        count = 0
        for s in scores:
            try:
                sc = float(s['score'])
                total += sc
                count += 1
            except (ValueError, TypeError):
                sc = 0
            chart_data.append({
                'assignment_title': s['assignment_title'],
                'score': sc
            })
        
        avg_score = round(total / count, 1) if count > 0 else 0
        
        # 计算与均分的差值
        for s in scores:
            try:
                diff = round(float(s['score']) - avg_score, 1)
            except (ValueError, TypeError):
                diff = 0
            s['diff'] = diff
        
        self.render_page('students/tracking.html',
                        active_menu='students',
                        student=student,
                        scores=scores,
                        chart_data=chart_data,
                        avg_score=avg_score,
                        title=f'学习追踪 - {student["name"]}')
    
    # ===== 班级管理 =====
    
    def classes_page(self, method, match, query):
        classes = db.get_classes()
        self.render_page('classes/index.html',
                        active_menu='classes',
                        classes=classes,
                        title='班级管理')
    
    def class_new_page(self, method, match, query):
        self.render_page('classes/form.html',
                        active_menu='classes',
                        class_obj={},
                        title='新增班级')
    
    def class_show_page(self, method, match, query):
        class_id = int(match.group(1))
        class_obj = db.get_class(class_id)
        if not class_obj:
            self.send_error(404)
            return
        
        students = db.get_class_students(class_id)
        all_students = db.get_students(status='active', limit=1000)
        courses = db.get_courses(class_id=class_id)
        
        self.render_page('classes/show.html',
                        active_menu='classes',
                        class_obj=class_obj,
                        students=students,
                        all_students=all_students,
                        courses=courses,
                        title=f'班级详情 - {class_obj["name"]}')
    
    def class_edit_page(self, method, match, query):
        class_id = int(match.group(1))
        class_obj = db.get_class(class_id)
        if not class_obj:
            self.send_error(404)
            return
        
        self.render_page('classes/form.html',
                        active_menu='classes',
                        class_obj=class_obj,
                        title='编辑班级')
    
    def classes_create(self, method, match, data):
        if not data.get('name', '').strip():
            self.send_error_page('班级名称不能为空', back_url='/classes/new')
            return
        try:
            db.create_class(data)
            self.redirect('/classes')
        except Exception as e:
            self.send_error_page(f'添加失败：{e}', back_url='/classes/new')
    
    def classes_update(self, method, match, data):
        class_id = int(match.group(1))
        if not data.get('name', '').strip():
            self.send_error_page('班级名称不能为空', back_url=f'/classes/{class_id}/edit')
            return
        try:
            db.update_class(class_id, data)
            self.redirect(f'/classes/{class_id}')
        except Exception as e:
            self.send_error_page(f'保存失败：{e}', back_url=f'/classes/{class_id}/edit')
    
    def classes_delete(self, method, match, data):
        class_id = int(match.group(1))
        db.delete_class(class_id)
        self.redirect('/classes')
    
    def class_students_manage(self, method, match, data):
        class_id = int(match.group(1))
        action = data.get('action')
        student_id = data.get('student_id')
        student_name = data.get('student_name', '')
        
        # 支持按姓名查找学员
        if not student_id and student_name:
            result = db.find_student_by_name(student_name.strip())
            if result:
                student_id = result['id']
        student_id = self._safe_int(student_id, default=0)
        
        if action == 'add' and student_id:
            db.add_student_to_class(class_id, student_id)
        elif action == 'remove' and student_id:
            db.remove_student_from_class(class_id, student_id)
        
        self.redirect(f'/classes/{class_id}')
    
    # ===== 课程管理 =====
    
    def courses_page(self, method, match, query):
        class_id = query.get('class_id', [''])[0]
        class_id_int = self._safe_int(class_id) if class_id else None
        courses = db.get_courses(class_id=class_id_int)
        classes = db.get_classes()
        
        self.render_page('courses/index.html',
                        active_menu='courses',
                        courses=courses,
                        classes=classes,
                        selected_class_id=class_id_int,
                        title='课程管理')
    
    def course_new_page(self, method, match, query):
        classes = db.get_classes()
        class_id = query.get('class_id', [''])[0]
        self.render_page('courses/form.html',
                        active_menu='courses',
                        course={'class_id': self._safe_int(class_id) if class_id else ''},
                        classes=classes,
                        title='新增课程')
    
    def course_show_page(self, method, match, query):
        course_id = int(match.group(1))
        course = db.get_course(course_id)
        if not course:
            self.send_error(404)
            return
        
        students = db.get_class_students(course['class_id'])
        attendances = db.get_course_attendances(course_id)
        attendance_map = {a['student_id']: a for a in attendances}
        
        # 将出勤信息附加到学员对象上，方便模板使用
        for student in students:
            attendance = attendance_map.get(student['id'], {})
            status = attendance.get('status', 'present')
            mode = attendance.get('mode', '')
            # 根据课程方式智能默认参与方式
            if not mode:
                if course['mode'] == 'online':
                    mode = 'online'
                else:
                    mode = 'offline'
            student['attendance'] = {
                'status': status,
                'mode': mode,
                'note': attendance.get('note', '')
            }
        
        self.render_page('courses/show.html',
                        active_menu='courses',
                        course=course,
                        students=students,
                        title=f'课程详情 - {course["title"]}')
    
    def course_edit_page(self, method, match, query):
        course_id = int(match.group(1))
        course = db.get_course(course_id)
        if not course:
            self.send_error(404)
            return
        
        classes = db.get_classes()
        self.render_page('courses/form.html',
                        active_menu='courses',
                        course=course,
                        classes=classes,
                        title='编辑课程')
    
    def courses_create(self, method, match, data):
        if not data.get('title', '').strip() or not data.get('class_id'):
            self.send_error_page('课程标题和所属班级不能为空', back_url='/courses/new')
            return
        try:
            db.create_course(data)
            self.redirect('/courses')
        except Exception as e:
            self.send_error_page(f'添加失败：{e}', back_url='/courses/new')
    
    def courses_update(self, method, match, data):
        course_id = int(match.group(1))
        if not data.get('title', '').strip() or not data.get('class_id'):
            self.send_error_page('课程标题和所属班级不能为空', back_url=f'/courses/{course_id}/edit')
            return
        try:
            db.update_course(course_id, data)
            self.redirect(f'/courses/{course_id}')
        except Exception as e:
            self.send_error_page(f'保存失败：{e}', back_url=f'/courses/{course_id}/edit')
    
    def courses_delete(self, method, match, data):
        course_id = int(match.group(1))
        db.delete_course(course_id)
        self.redirect('/courses')
    
    def attendance_save(self, method, match, data):
        course_id = int(match.group(1))
        # data 中可能包含多个 status_xxx / mode_xxx / note_xxx 字段
        for key, value in data.items():
            if key.startswith('status_'):
                student_id = self._safe_int(key.replace('status_', ''))
                status = value
                mode = data.get(f'mode_{student_id}', '')
                note = data.get(f'note_{student_id}', '')
                db.set_attendance(course_id, student_id, status, note, mode or None)
        
        self.redirect(f'/courses/{course_id}')
    
    # ===== 成绩管理 =====
    
    def grades_page(self, method, match, query):
        class_id = query.get('class_id', [''])[0]
        exam_name = query.get('exam_name', [''])[0]
        student_id = query.get('student_id', [''])[0]
        class_id_int = self._safe_int(class_id) if class_id else None
        student_id_int = self._safe_int(student_id) if student_id else None

        grades = db.get_grades(
            class_id=class_id_int,
            exam_name=exam_name if exam_name else None,
            student_id=student_id_int
        )
        classes = db.get_classes()
        students = db.get_students(limit=1000)
        stats = db.get_grade_statistics(class_id=class_id_int, exam_name=exam_name if exam_name else None)
        distribution = db.get_grade_distribution()

        # 按班级分组
        grouped_map = {}
        for g in grades:
            key = g['class_name'] or '未分配班级'
            grouped_map.setdefault(key, []).append(g)
        grouped_grades = [
            {'class_name': class_name, 'grades': class_grades}
            for class_name, class_grades in grouped_map.items()
        ]

        self.render_page('grades/index.html',
                        active_menu='grades',
                        grades=grades,
                        grouped_grades=grouped_grades,
                        classes=classes,
                        students=students,
                        selected_class_id=class_id_int,
                        exam_name=exam_name,
                        student_id=student_id,
                        stats=stats,
                        distribution=distribution,
                        title='成绩管理')
    
    def grade_new_page(self, method, match, query):
        classes = db.get_classes()
        students = db.get_students(status='active', limit=1000)
        self.render_page('grades/form.html',
                        active_menu='grades',
                        grade={},
                        classes=classes,
                        students=students,
                        title='新增成绩')
    
    def grade_edit_page(self, method, match, query):
        grade_id = int(match.group(1))
        grade = db.get_grade(grade_id)
        if not grade:
            self.send_error(404)
            return
        
        classes = db.get_classes()
        students = db.get_students(status='active', limit=1000)
        self.render_page('grades/form.html',
                        active_menu='grades',
                        grade=grade,
                        classes=classes,
                        students=students,
                        title='编辑成绩')
    
    def grades_create(self, method, match, data):
        if not data.get('student_id') or not data.get('exam_name', '').strip() or not data.get('score'):
            self.send_error_page('学员、考试名称和得分不能为空', back_url='/grades/new')
            return
        try:
            db.create_grade(data)
            self.redirect('/grades')
        except Exception as e:
            self.send_error_page(f'添加失败：{e}', back_url='/grades/new')
    
    def grades_update(self, method, match, data):
        grade_id = int(match.group(1))
        if not data.get('student_id') or not data.get('exam_name', '').strip() or not data.get('score'):
            self.send_error_page('学员、考试名称和得分不能为空', back_url=f'/grades/{grade_id}/edit')
            return
        try:
            db.update_grade(grade_id, data)
            self.redirect('/grades')
        except Exception as e:
            self.send_error_page(f'保存失败：{e}', back_url=f'/grades/{grade_id}/edit')
    
    def grades_delete(self, method, match, data):
        grade_id = int(match.group(1))
        db.delete_grade(grade_id)
        self.redirect('/grades')
    
    # ===== 作业管理 =====
    
    def assignments_page(self, method, match, query):
        class_id = query.get('class_id', [''])[0]
        sort_by = query.get('sort', [''])[0]
        class_id_int = self._safe_int(class_id) if class_id else None
        assignments = db.get_assignments_with_sort(
            class_id=class_id_int,
            sort_by=sort_by if sort_by else None
        )
        classes = db.get_classes()

        # 补充每个作业的提交统计
        for a in assignments:
            stats = db.get_assignment_stats(a['id'])
            a['stats'] = stats or {}
            # 计算平均分
            submissions = db.get_assignment_submissions(a['id'])
            scores = [float(s['score']) for s in submissions if s.get('score')]
            a['avg_score'] = round(sum(scores) / len(scores), 1) if scores else None

        self.render_page('assignments/index.html',
                        active_menu='assignments',
                        assignments=assignments,
                        classes=classes,
                        selected_class_id=class_id_int,
                        sort_by=sort_by,
                        title='作业管理')
    
    def assignment_new_page(self, method, match, query):
        classes = db.get_classes()
        self.render_page('assignments/form.html',
                        active_menu='assignments',
                        assignment={},
                        classes=classes,
                        title='新增作业')
    
    def assignment_show_page(self, method, match, query):
        assignment_id = int(match.group(1))
        assignment = db.get_assignment(assignment_id)
        if not assignment:
            self.send_error(404)
            return
        
        # 获取班级学员和作业提交情况
        students = db.get_class_students(assignment['class_id'])
        submissions = db.get_assignment_submissions(assignment_id)
        submission_map = {s['student_id']: s for s in submissions}
        
        stats = {'submitted': 0, 'late': 0, 'pending': len(students), 'avg_score': '-'}
        total_score = 0
        score_count = 0
        
        for student in students:
            submission = submission_map.get(student['id'], {})
            status = submission.get('status', 'submitted')
            score = submission.get('score')
            student['submission'] = {
                'status': status,
                'score': score if score else '',
                'submitted_at': submission.get('submitted_at', ''),
                'note': submission.get('note', '')
            }
            # 统计
            if score is not None and score != '':
                try:
                    total_score += float(score)
                    score_count += 1
                except (ValueError, TypeError):
                    pass
            if status == 'submitted':
                stats['submitted'] += 1
                stats['pending'] -= 1
            elif status == 'late':
                stats['late'] += 1
                stats['pending'] -= 1
        
        if score_count > 0:
            stats['avg_score'] = round(total_score / score_count, 1)
        
        self.render_page('assignments/show.html',
                        active_menu='assignments',
                        assignment=assignment,
                        students=students,
                        stats=stats,
                        title=f'作业详情 - {assignment["title"]}')
    
    def assignment_submissions_update(self, method, match, data):
        """批量更新作业提交状态和成绩"""
        assignment_id = int(match.group(1))
        students = db.get_class_students(db.get_assignment(assignment_id)['class_id'])
        for student in students:
            sid = str(student['id'])
            status = data.get(f'status_{sid}')
            score = data.get(f'score_{sid}')
            note = data.get(f'note_{sid}')
            if status:
                db.set_assignment_submission(assignment_id, student['id'], status=status, score=score, note=note)
        self.redirect(f'/assignments/{assignment_id}')
    
    def assignment_import_scores_page(self, method, match, query):
        """成绩导入表单页"""
        assignment_id = int(match.group(1))
        assignment = db.get_assignment(assignment_id)
        if not assignment:
            self.send_error(404)
            return
        self.render_page('assignments/import_scores.html',
                        active_menu='assignments',
                        assignment=assignment,
                        title=f'导入成绩 - {assignment["title"]}')
    
    def assignment_import_scores(self, method, match, data):
        """导入作业成绩"""
        assignment_id = int(match.group(1))
        csv_data = data.get('csv_data', '')
        success, errors = db.import_assignment_scores(assignment_id, csv_data)
        self.render_page('assignments/import_result.html',
                        active_menu='assignments',
                        assignment_id=assignment_id,
                        success=success,
                        errors=errors,
                        title='成绩导入结果')
    
    def assignment_edit_page(self, method, match, query):
        assignment_id = int(match.group(1))
        assignment = db.get_assignment(assignment_id)
        if not assignment:
            self.send_error(404)
            return
        classes = db.get_classes()
        self.render_page('assignments/form.html',
                        active_menu='assignments',
                        assignment=assignment,
                        classes=classes,
                        title='编辑作业')
    
    def assignments_create(self, method, match, data):
        if not data.get('title', '').strip() or not data.get('class_id'):
            self.send_error_page('作业标题和所属班级不能为空', back_url='/assignments/new')
            return
        try:
            db.create_assignment(data)
            self.redirect('/assignments')
        except Exception as e:
            self.send_error_page(f'添加失败：{e}', back_url='/assignments/new')
    
    def assignments_update(self, method, match, data):
        assignment_id = int(match.group(1))
        if not data.get('title', '').strip() or not data.get('class_id'):
            self.send_error_page('作业标题和所属班级不能为空', back_url=f'/assignments/{assignment_id}/edit')
            return
        try:
            db.update_assignment(assignment_id, data)
            self.redirect('/assignments')
        except Exception as e:
            self.send_error_page(f'保存失败：{e}', back_url=f'/assignments/{assignment_id}/edit')
    
    def assignments_delete(self, method, match, data):
        assignment_id = int(match.group(1))
        db.delete_assignment(assignment_id)
        self.redirect('/assignments')
    
    # ===== 出勤记录 =====
    
    def attendances_page(self, method, match, query):
        class_id = query.get('class_id', [''])[0]
        class_id_int = self._safe_int(class_id) if class_id else None
        courses = db.get_courses(class_id=class_id_int)
        classes = db.get_classes()
        
        self.render_page('attendances/index.html',
                        active_menu='attendances',
                        courses=courses,
                        classes=classes,
                        selected_class_id=class_id_int,
                        title='出勤记录')
    
    # ===== 缴费管理 =====
    
    def payments_page(self, method, match, query):
        student_id = query.get('student_id', [''])[0]
        status = query.get('status', [''])[0]
        student_id_int = self._safe_int(student_id) if student_id else None
        payments = db.get_payments(
            student_id=student_id_int,
            status=status if status else None
        )
        students = db.get_students(limit=1000)
        
        self.render_page('payments/index.html',
                        active_menu='payments',
                        payments=payments,
                        students=students,
                        selected_student_id=student_id_int,
                        status=status,
                        title='缴费管理')
    
    def payment_new_page(self, method, match, query):
        students = db.get_students(status='active', limit=1000)
        classes = db.get_classes()
        self.render_page('payments/form.html',
                        active_menu='payments',
                        payment={},
                        students=students,
                        classes=classes,
                        title='新增缴费')
    
    def payment_edit_page(self, method, match, query):
        payment_id = int(match.group(1))
        payment = db.get_payment(payment_id)
        if not payment:
            self.send_error(404)
            return
        
        students = db.get_students(status='active', limit=1000)
        classes = db.get_classes()
        self.render_page('payments/form.html',
                        active_menu='payments',
                        payment=payment,
                        students=students,
                        classes=classes,
                        title='编辑缴费')
    
    def payments_create(self, method, match, data):
        if not data.get('student_id') or not data.get('amount'):
            self.send_error_page('学员和缴费金额不能为空', back_url='/payments/new')
            return
        try:
            db.create_payment(data)
            self.redirect('/payments')
        except Exception as e:
            self.send_error_page(f'添加失败：{e}', back_url='/payments/new')
    
    def payments_update(self, method, match, data):
        payment_id = int(match.group(1))
        if not data.get('student_id') or not data.get('amount'):
            self.send_error_page('学员和缴费金额不能为空', back_url=f'/payments/{payment_id}/edit')
            return
        try:
            db.update_payment(payment_id, data)
            self.redirect('/payments')
        except Exception as e:
            self.send_error_page(f'保存失败：{e}', back_url=f'/payments/{payment_id}/edit')
    
    def payments_delete(self, method, match, data):
        payment_id = int(match.group(1))
        db.delete_payment(payment_id)
        self.redirect('/payments')

    # ===== 排名对比 =====

    @staticmethod
    def _parse_exam_data(raw_text):
        """解析成绩文本，返回 {name: score} 字典（按输入顺序，成绩为 float）。
        自动去除表头行，支持逗号、制表符、空格分隔。
        """
        result = {}
        seen = set()
        header_keywords = {'姓名', '名字', 'name', '学生', '成绩', '分数', 'score', '得分', '总分'}
        for line in raw_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # 检测分隔符
            if '\t' in line:
                parts = line.split('\t')
            elif ',' in line:
                parts = line.split(',')
            else:
                parts = line.rsplit(None, 1)  # 从右侧按空格分割一次
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            score_str = parts[1].strip()
            # 跳过表头行
            if name.lower() in header_keywords or score_str.lower() in header_keywords:
                continue
            try:
                score = float(score_str)
            except ValueError:
                continue
            key = name
            if key not in seen:
                result[key] = score
                seen.add(key)
        return result

    @staticmethod
    def _compute_ranks(scores_dict):
        """计算排名。返回 {name: rank}，分数高者排名靠前，同分同名次。
        例：100,100,90 -> 排名 1,1,3
        """
        if not scores_dict:
            return {}
        sorted_items = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
        ranks = {}
        current_rank = 1
        prev_score = None
        same_rank_count = 0
        for i, (name, score) in enumerate(sorted_items):
            if prev_score is not None and score < prev_score:
                current_rank += same_rank_count
                same_rank_count = 1
            else:
                same_rank_count += 1
            ranks[name] = current_rank
            prev_score = score
        return ranks

    def rank_compare_page(self, method, match, query):
        """排名对比 GET：显示空输入页"""
        self.render_page('rank-compare/index.html',
                        active_menu='rank-compare',
                        exam1_name='',
                        exam1_data='',
                        exam2_name='',
                        exam2_data='',
                        title='排名对比')

    def rank_compare_analyze(self, method, match, data):
        """排名对比 POST：处理分析请求"""
        exam1_name = data.get('exam1_name', '第一次考试').strip() or '第一次考试'
        exam2_name = data.get('exam2_name', '第二次考试').strip() or '第二次考试'
        exam1_raw = data.get('exam1_data', '').strip()
        exam2_raw = data.get('exam2_data', '').strip()

        sort = data.get('sort', 'rank_change')

        if not exam1_raw or not exam2_raw:
            self.send_error_page('请同时输入两次考试的成绩数据', '/rank-compare')
            return

        # 解析成绩
        scores1 = self._parse_exam_data(exam1_raw)
        scores2 = self._parse_exam_data(exam2_raw)

        if not scores1 and not scores2:
            self.send_error_page('未能解析到有效成绩数据，请检查输入格式', '/rank-compare')
            return

        # 计算排名
        ranks1 = self._compute_ranks(scores1)
        ranks2 = self._compute_ranks(scores2)

        # 合并所有姓名，保留首次考试的出现顺序
        all_names = list(scores1.keys())
        for name in scores2:
            if name not in all_names:
                all_names.append(name)

        # 构建对比结果
        comparisons = []
        improved = 0
        declined = 0
        unchanged = 0
        new_only = 0
        dropped_only = 0

        for name in all_names:
            has_s1 = name in scores1
            has_s2 = name in scores2

            if has_s1 and has_s2:
                score_c = round(scores2[name] - scores1[name], 1)
                rank_c = ranks1[name] - ranks2[name]  # 正数=排名上升（进步）
                is_new = False
                is_dropped = False

                if rank_c > 0:
                    improved += 1
                elif rank_c < 0:
                    declined += 1
                else:
                    unchanged += 1

                comparisons.append({
                    'name': name,
                    'score1': scores1[name],
                    'rank1': ranks1[name],
                    'score2': scores2[name],
                    'rank2': ranks2[name],
                    'score_change': score_c,
                    'rank_change': rank_c,
                    'abs_rank_change': abs(rank_c) if rank_c != 0 else 0,
                    'is_new': False,
                    'is_dropped': False,
                })
            elif has_s1 and not has_s2:
                # 退出（仅第一次有）
                dropped_only += 1
                comparisons.append({
                    'name': name,
                    'score1': scores1[name],
                    'rank1': ranks1[name],
                    'score2': None,
                    'rank2': None,
                    'score_change': None,
                    'rank_change': None,
                    'abs_rank_change': 0,
                    'is_new': False,
                    'is_dropped': True,
                })
            elif not has_s1 and has_s2:
                # 新增（仅第二次有）
                new_only += 1
                comparisons.append({
                    'name': name,
                    'score1': None,
                    'rank1': None,
                    'score2': scores2[name],
                    'rank2': ranks2[name],
                    'score_change': None,
                    'rank_change': None,
                    'abs_rank_change': 0,
                    'is_new': True,
                    'is_dropped': False,
                })

        # 排序
        if sort == 'name':
            comparisons.sort(key=lambda c: c['name'])
        elif sort == 'rank1':
            def rank1_key(c):
                if c['is_new']:
                    return float('inf')
                return c['rank1']
            comparisons.sort(key=rank1_key)
        elif sort == 'score_change':
            def sc_key(c):
                if c['score_change'] is None:
                    return float('-inf')
                return -c['score_change']  # 正变化在前
            comparisons.sort(key=sc_key)
        elif sort == 'rank2':
            def rank2_key(c):
                if c['is_dropped']:
                    return float('inf')
                return c['rank2']
            comparisons.sort(key=rank2_key)
        else:  # rank_change
            def rc_key(c):
                if c['rank_change'] is None:
                    return float('-inf')
                return -c['rank_change']  # 进步最多的在前
            comparisons.sort(key=rc_key)

        # 添加序号
        for i, c in enumerate(comparisons):
            c['index'] = i + 1

        total = len(comparisons)

        self.render_page('rank-compare/index.html',
                        active_menu='rank-compare',
                        exam1_name=exam1_name,
                        exam1_data=exam1_raw,
                        exam2_name=exam2_name,
                        exam2_data=exam2_raw,
                        comparisons=comparisons,
                        sort=sort,
                        stats={
                            'total': total,
                            'improved': improved,
                            'declined': declined,
                            'unchanged': unchanged,
                            'new_only': new_only,
                            'dropped_only': dropped_only,
                        },
                        title='排名对比')

    # ===== 学员批量操作 =====

    def students_batch_page(self, method, match, query):
        classes = db.get_classes(status='active')
        search = query.get('search', [''])[0]
        cohort = query.get('cohort', [''])[0]
        grade = query.get('grade', [''])[0]
        status = query.get('status', [''])[0] or 'active'
        students = db.get_students(search=search, cohort=cohort, grade=grade, status=status, limit=1000)
        cohorts = db.get_distinct_cohorts()
        self.render_page('students/batch.html',
                        active_menu='students',
                        classes=classes,
                        students=students,
                        cohorts=cohorts,
                        search=search,
                        cohort=cohort,
                        grade=grade,
                        status=status,
                        title='批量操作学员')

    def students_batch_action(self, method, match, data):
        student_ids = data.get('student_ids', [])
        if isinstance(student_ids, str):
            student_ids = [student_ids]
        action = data.get('action')

        if not student_ids:
            self.send_error_page('请至少选择一名学员', back_url='/students/batch')
            return

        try:
            if action == 'add_to_class':
                class_id = data.get('target_class_id')
                if not class_id:
                    self.send_error_page('请选择目标班级', back_url='/students/batch')
                    return
                count = db.batch_add_students_to_class(student_ids, class_id)
                self.redirect(f'/classes/{class_id}')
                return
            elif action == 'update_info':
                fields = {}
                if data.get('new_grade'):
                    fields['grade'] = data.get('new_grade')
                if data.get('new_cohort'):
                    fields['cohort'] = data.get('new_cohort')
                if data.get('new_status'):
                    fields['status'] = data.get('new_status')
                if data.get('new_school'):
                    fields['school'] = data.get('new_school')
                if not fields:
                    self.send_error_page('请至少选择一项要修改的信息', back_url='/students/batch')
                    return
                count = db.batch_update_students(student_ids, fields)
                self.redirect('/students')
                return
            else:
                self.send_error_page('未知操作', back_url='/students/batch')
        except Exception as e:
            self.send_error_page(f'批量操作失败：{e}', back_url='/students/batch')

    def students_import_page(self, method, match, query):
        self.render_page('students/import.html',
                        active_menu='students',
                        preview=None,
                        title='批量导入学员')

    def students_import_preview(self, method, match, data):
        raw = data.get('csv_data', '')
        rows = self._parse_csv_text(raw)
        preview = []
        for idx, row in enumerate(rows, 1):
            preview.append({
                'line': idx,
                'name': row.get('name', ''),
                'grade': row.get('grade', ''),
                'cohort': row.get('cohort', ''),
                'school': row.get('school', ''),
                'phone': row.get('phone', ''),
                'valid': bool(row.get('name', '').strip())
            })
        self.render_page('students/import.html',
                        active_menu='students',
                        preview=preview,
                        csv_data=raw,
                        title='批量导入学员')

    def students_import(self, method, match, data):
        raw = data.get('csv_data', '')
        rows = self._parse_csv_text(raw)
        success, errors = db.batch_import_students(rows)
        self.render_page('students/import_result.html',
                        active_menu='students',
                        success=success,
                        errors=errors,
                        title='导入结果')

    def _parse_csv_text(self, text):
        """解析 CSV 文本为字典列表，支持姓名,年级,级,学校,手机,家长电话 等列"""
        if not text.strip():
            return []
        reader = db.smart_csv_read(text)
        rows = list(reader)
        if not rows:
            return []
        header = [h.strip() for h in rows[0]]
        # 映射常用列名
        name_cols = ['姓名', 'name', '学员姓名']
        grade_cols = ['年级', 'grade', '当前年级']
        cohort_cols = ['级', '级次', 'cohort', '入学级']
        school_cols = ['学校', 'school']
        phone_cols = ['手机', '电话', 'phone', '联系电话']
        parent_phone_cols = ['家长电话', 'parent_phone']
        wechat_cols = ['微信', '微信号', 'wechat']
        address_cols = ['地址', 'address']
        note_cols = ['备注', 'note']
        status_cols = ['状态', 'status']

        def find_col(candidates):
            for c in candidates:
                if c in header:
                    return header.index(c)
            return None

        name_idx = find_col(name_cols)
        grade_idx = None; cohort_idx = None; school_idx = None
        phone_idx = None; parent_phone_idx = None; wechat_idx = None
        address_idx = None; note_idx = None; status_idx = None
        
        if name_idx is None:
            # 没有表头，按列位置自动推断
            name_idx = 0
            header_start = 0
            ncols = len(header)
            # 2列：姓名 + 数字=级次 / 含"高/初"=年级
            if ncols == 2:
                v = header[1].strip()
                if v.isdigit() or re.match(r'^\d{2}$', v):
                    cohort_idx = 1
                elif '高' in v or '初' in v:
                    grade_idx = 1
            elif ncols == 3:
                cohort_idx = 1
                grade_idx = 2
            elif ncols >= 4:
                cohort_idx = 1
                grade_idx = 2
                school_idx = 3
        else:
            header_start = 1
            grade_idx = find_col(grade_cols)
            cohort_idx = find_col(cohort_cols)
            school_idx = find_col(school_cols)
            phone_idx = find_col(phone_cols)
            parent_phone_idx = find_col(parent_phone_cols)
            wechat_idx = find_col(wechat_cols)
            address_idx = find_col(address_cols)
            note_idx = find_col(note_cols)
            status_idx = find_col(status_cols)

        result = []
        for row in rows[header_start:]:
            if not row or not row[0].strip():
                continue
            item = {'name': row[name_idx].strip() if name_idx < len(row) else ''}
            if grade_idx is not None and grade_idx < len(row):
                item['grade'] = row[grade_idx].strip()
            if cohort_idx is not None and cohort_idx < len(row):
                item['cohort'] = row[cohort_idx].strip()
            if school_idx is not None and school_idx < len(row):
                item['school'] = row[school_idx].strip()
            if phone_idx is not None and phone_idx < len(row):
                item['phone'] = row[phone_idx].strip()
            if parent_phone_idx is not None and parent_phone_idx < len(row):
                item['parent_phone'] = row[parent_phone_idx].strip()
            if wechat_idx is not None and wechat_idx < len(row):
                item['wechat'] = row[wechat_idx].strip()
            if address_idx is not None and address_idx < len(row):
                item['address'] = row[address_idx].strip()
            if note_idx is not None and note_idx < len(row):
                item['note'] = row[note_idx].strip()
            if status_idx is not None and status_idx < len(row):
                status_val = row[status_idx].strip()
                if status_val in ('已报名', 'registered'):
                    item['status'] = 'registered'
                elif status_val in ('已退学', 'inactive'):
                    item['status'] = 'inactive'
            result.append(item)
        return result

    # ===== 成绩导入导出 =====

    def grades_import_page(self, method, match, query):
        classes = db.get_classes(status='active')
        self.render_page('grades/import.html',
                        active_menu='grades',
                        classes=classes,
                        preview=None,
                        title='导入成绩')

    def grades_import(self, method, match, data):
        raw = data.get('csv_data', '')
        class_id = data.get('class_id') or None
        success, errors = db.import_grades_from_csv(raw, class_id)
        self.render_page('grades/import_result.html',
                        active_menu='grades',
                        success=success,
                        errors=errors,
                        title='成绩导入结果')

    def grades_export(self, method, match, query):
        class_id = query.get('class_id', [''])[0]
        exam_name = query.get('exam_name', [''])[0]
        class_id_int = self._safe_int(class_id) if class_id else None
        content = db.export_grades_to_csv(
            class_id=class_id_int,
            exam_name=exam_name if exam_name else None
        )
        filename = f'grades_export_{datetime.now().strftime("%Y%m%d")}.csv'
        self.send_csv(content, filename)

    # ===== API =====
    
    def api_handler(self, method, match, query):
        """简单 API 处理"""
        path = self.path
        
        if path == '/api/students':
            students = db.get_students(status='active', limit=1000)
            self.send_json([{'id': s['id'], 'name': s['name']} for s in students])
        elif path == '/api/classes':
            classes = db.get_classes(status='active')
            self.send_json([{'id': c['id'], 'name': c['name']} for c in classes])
        else:
            self.send_error(404)
    
    def send_json(self, data):
        content = json.dumps(data, ensure_ascii=False, default=str)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(content.encode('utf-8')))
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，支持并发请求处理"""
    daemon_threads = True


def run_server(port=3000):
    server = ThreadingHTTPServer(('127.0.0.1', port), AppHandler)
    
    # 检查数据库状态
    db_path = db.DATABASE_PATH
    if not DB_EXISTED:
        print(f'📦 首次运行，已自动创建数据库')
    print(f'💾 数据库位置: {db_path}')
    
    print(f'🚀 学员管理系统已启动')
    print(f'📍 访问地址: http://localhost:{port}')
    print('按 Ctrl+C 停止服务')
    
    # 延迟 1 秒后自动打开浏览器
    url = f'http://localhost:{port}'
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止')
        server.shutdown()


if __name__ == '__main__':
    run_server()
