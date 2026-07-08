"""
seed.py - 生成测试数据
"""

import database as db
from datetime import datetime, timedelta
import random


def seed_data():
    db.init_db()
    
    # 检查是否已有数据
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM students')
    if cursor.fetchone()['count'] > 0:
        print("数据库已有数据，跳过 seed")
        conn.close()
        return
    conn.close()
    
    print("正在生成测试数据...")
    
    # 创建班级
    classes = [
        {
            'name': '新高一物理理优班',
            'grade': '高一',
            'cohort': '26',
            'subject': '物理',
            'max_students': 15,
            'teacher_name': '李老师',
            'description': '高一物理预科，衔接初中与高中物理思维',
            'status': 'active'
        },
        {
            'name': '高二升高三一轮复习班',
            'grade': '高三',
            'cohort': '25',
            'subject': '物理',
            'max_students': 6,
            'teacher_name': '李老师',
            'description': '高二升高三暑期一轮复习，一对四精品小班',
            'status': 'active'
        },
        {
            'name': '高一物理提高班',
            'grade': '高一',
            'cohort': '26',
            'subject': '物理',
            'max_students': 12,
            'teacher_name': '李老师',
            'description': '高一物理同步提高',
            'status': 'active'
        }
    ]
    
    class_ids = []
    for c in classes:
        class_ids.append(db.create_class(c))
    
    # 创建学员
    student_names = [
        ('张', ['伟', '强', '磊', '明', '杰', '浩', '鹏', '宇', '飞', '阳']),
        ('李', ['娜', '婷', '静', '敏', '丽', '芳', '燕', '玲', '红', '梅']),
        ('王', ['磊', '军', '勇', '刚', '平', '辉', '涛', '波', '超', '鹏']),
        ('刘', ['洋', '博', '文', '武', '斌', '鑫', '凯', '翔', '瑞', '昊']),
        ('陈', ['晨', '曦', '露', '雪', '洁', '颖', '琳', '倩', '雯', '嫣']),
        ('杨', ['帆', '柳', '彬', '峰', '松', '柏', '楠', '森', '林', '桦']),
        ('赵', ['雪', '敏', '慧', '艳', '霞', '青', '蓉', '兰', '凤', '英']),
        ('黄', ['辉', '耀', '灿', '炜', '烨', '烁', '焕', '煜', '炅', '炫'])
    ]
    
    schools = ['合肥一中', '合肥六中', '合肥八中', '合肥一六八中学', '市区中学', '科大附中']
    grades = ['高一', '高二', '高三']
    cohort_map = {'高一': '26', '高二': '25', '高三': '24'}

    student_ids = []
    for i in range(35):
        surname, names = random.choice(student_names)
        name = surname + random.choice(names)
        grade = random.choice(grades)
        school = random.choice(schools)

        student_id = db.create_student({
            'name': name,
            'phone': f'138{random.randint(10000000, 99999999)}',
            'wechat': f'wx_{name.lower()}',
            'school': school,
            'grade': grade,
            'cohort': cohort_map[grade],
            'parent_name': f'{surname}家长',
            'parent_phone': f'139{random.randint(10000000, 99999999)}',
            'address': '合肥市蜀山区',
            'status': 'active',
            'note': ''
        })
        student_ids.append(student_id)
    
    # 将学员分配到班级
    # 新高一物理理优班：10人
    for i in range(10):
        db.add_student_to_class(class_ids[0], student_ids[i])
    
    # 高二升高三一轮复习班：4人
    for i in range(10, 14):
        db.add_student_to_class(class_ids[1], student_ids[i])
    
    # 高一物理提高班：8人
    for i in range(14, 22):
        db.add_student_to_class(class_ids[2], student_ids[i])
    
    # 创建课程
    base_date = datetime(2026, 7, 14, 14, 0, 0)
    course_titles = [
        '运动学基本概念与公式',
        '匀变速直线运动规律',
        '追及相遇问题专题',
        '牛顿运动定律基础',
        '牛顿定律应用：连接体问题',
        '曲线运动与抛体运动',
        '圆周运动基本规律',
        '万有引力与航天',
        '机械能守恒定律',
        '动量与动量守恒',
        '电场基本概念',
        '库仑定律与电场强度',
        '电势能与电势',
        '带电粒子在电场中的运动',
        '磁场与安培力'
    ]
    
    for i in range(15):
        course_time = base_date + timedelta(days=i * 2, hours=(i % 2) * 3)
        class_id = class_ids[0] if i < 5 else (class_ids[1] if i < 10 else class_ids[2])
        mode = random.choice(['offline', 'offline', 'hybrid', 'online'])
        db.create_course({
            'class_id': class_id,
            'title': course_titles[i],
            'scheduled_at': course_time.strftime('%Y-%m-%dT%H:%M'),
            'duration': 120,
            'location': 'EduFlow教室' + random.choice(['A', 'B']) if mode != 'online' else '腾讯会议 123-456-789',
            'mode': mode,
            'status': 'planned' if i > 2 else 'completed',
            'description': '系统复习重点知识点'
        })
    
    # 创建成绩
    exam_names = ['入学测试', '第一次月考', '期中考试', '第二次月考', '期末考试']
    for exam in exam_names:
        for student_id in student_ids[:20]:
            score = round(random.uniform(45, 100), 1)
            class_id = None
            # 找到学员所在班级
            classes = db.get_student_classes(student_id)
            if classes:
                class_id = classes[0]['id']
            
            db.create_grade({
                'student_id': student_id,
                'class_id': class_id,
                'exam_name': exam,
                'subject': '物理',
                'score': score,
                'max_score': 100,
                'exam_date': (datetime(2026, 7, 1) + timedelta(days=random.randint(0, 60))).strftime('%Y-%m-%d'),
                'note': ''
            })
    
    # 创建作业
    assignments = [
        {'title': '运动学练习题', 'class_id': class_ids[0]},
        {'title': '牛顿定律应用', 'class_id': class_ids[0]},
        {'title': '曲线运动专题', 'class_id': class_ids[1]},
        {'title': '电场基础练习', 'class_id': class_ids[2]},
    ]
    
    for idx, assignment in enumerate(assignments):
        db.create_assignment({
            'class_id': assignment['class_id'],
            'title': assignment['title'],
            'content': '完成课后练习第 ' + str(random.randint(1, 5)) + ' 到第 ' + str(random.randint(6, 10)) + ' 题',
            'deadline': (datetime(2026, 7, 15) + timedelta(days=idx * 7)).strftime('%Y-%m-%d'),
            'status': 'active'
        })
    
    # 创建缴费记录
    for i in range(25):
        student_id = student_ids[i]
        classes = db.get_student_classes(student_id)
        class_id = classes[0]['id'] if classes else None
        status = random.choice(['paid', 'paid', 'paid', 'unpaid', 'overdue'])
        
        db.create_payment({
            'student_id': student_id,
            'class_id': class_id,
            'amount': random.choice([3000, 4500, 6000, 8000]),
            'type': random.choice(['tuition', 'tuition', 'material', 'other']),
            'status': status,
            'paid_at': (datetime(2026, 6, 1) + timedelta(days=random.randint(0, 30))).strftime('%Y-%m-%d') if status == 'paid' else None,
            'due_date': (datetime(2026, 7, 1) + timedelta(days=random.randint(0, 30))).strftime('%Y-%m-%d'),
            'note': '暑期班学费'
        })
    
    print("测试数据生成完成！")
    print(f"- 班级：{len(class_ids)} 个")
    print(f"- 学员：{len(student_ids)} 人")
    print(f"- 课程：15 节")
    print(f"- 成绩：{len(exam_names) * 20} 条")
    print(f"- 作业：{len(assignments)} 条")
    print(f"- 缴费：25 条")


if __name__ == '__main__':
    seed_data()
