#!/usr/bin/env python3
"""
数据库管理器
负责所有数据库操作，包括工单管理、用户管理、权限管理等
"""

import sqlite3
import os
from datetime import datetime, timedelta
import pytz
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class DatabaseManager:
    """数据库管理类"""
    
    def __init__(self, db_path='feedback.db'):
        self.db_path = db_path
        self._initialized = False
        self.init_db()
    
    def init_db(self):
        """初始化数据库"""
        if self._initialized:
            return
            
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 创建问题表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS problems (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        description TEXT NOT NULL,
                        author TEXT NOT NULL,
                        contact_info TEXT,
                        department TEXT,
                        status TEXT DEFAULT '待处理',
                        priority TEXT DEFAULT '普通',
                        processing_unit TEXT,
                        processing_person TEXT,
                        response_department TEXT,
                        initial_processing_unit TEXT,
                        initial_status TEXT,
                        views INTEGER DEFAULT 0,
                        likes INTEGER DEFAULT 0,
                        dislikes INTEGER DEFAULT 0,
                        comments INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        post_time TEXT,
                        work_order TEXT,
                        hashtag TEXT
                    )
                ''')
                
                # 创建状态日志表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS status_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        problem_id INTEGER NOT NULL,
                        old_status TEXT,
                        new_status TEXT NOT NULL,
                        operator TEXT NOT NULL,
                        comment TEXT,
                        department TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (problem_id) REFERENCES problems (id)
                    )
                ''')
                
                # 创建处理记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS processing_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        problem_id INTEGER NOT NULL,
                        processor TEXT NOT NULL,
                        measure TEXT NOT NULL,
                        department TEXT,
                        assigned_to TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (problem_id) REFERENCES problems (id)
                    )
                ''')
                
                # 创建问题部门关联表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS problem_departments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        problem_id INTEGER NOT NULL,
                        department TEXT NOT NULL,
                        is_primary BOOLEAN DEFAULT 0,
                        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        assigned_by TEXT,
                        FOREIGN KEY (problem_id) REFERENCES problems (id)
                    )
                ''')
                
                # 创建用户表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        real_name TEXT NOT NULL,
                        email TEXT,
                        phone TEXT,
                        department TEXT,
                        role TEXT NOT NULL CHECK (role IN ('user', 'processor', 'manager', 'admin')),
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        created_by INTEGER,
                        FOREIGN KEY (created_by) REFERENCES users (id)
                    )
                ''')
                
                # 创建用户会话表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        session_token TEXT UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        ip_address TEXT,
                        user_agent TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                
                # 创建权限表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS permissions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        permission TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(role, permission)
                    )
                ''')
                
                # 创建评论表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS comments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        problem_id INTEGER NOT NULL,
                        author TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (problem_id) REFERENCES problems (id)
                    )
                ''')
                
                # 创建评论回复表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS comment_replies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        comment_id INTEGER NOT NULL,
                        author TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (comment_id) REFERENCES comments (id)
                    )
                ''')
                
                # 创建反应表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        problem_id INTEGER NOT NULL,
                        user_id TEXT NOT NULL,
                        reaction_type TEXT NOT NULL CHECK (reaction_type IN ('like', 'dislike')),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(problem_id, user_id)
                    )
                ''')
                
                # 创建问题文件表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS problem_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        problem_id INTEGER NOT NULL,
                        file_name TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_size INTEGER,
                        file_type TEXT,
                        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (problem_id) REFERENCES problems (id)
                    )
                ''')
                
                # 设置行工厂为字典格式
                conn.row_factory = sqlite3.Row
                
                conn.commit()
                
                # 执行迁移
                self._migrate_to_multi_department()
                
                self._initialized = True
                # 数据库初始化完成
                
        except Exception as e:
            print(f"数据库初始化失败: {e}")
            raise
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def save_problem(self, title, category, description, author, contact_info, 
                    department="", uploaded_files=None, response_department="调度中心"):
        """保存问题到数据库"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 根据首响部门确定初始状态
                if response_department and response_department not in ["未定", "调度中心"]:
                    initial_processing_unit = response_department
                    initial_status = "已派发"
                else:
                    initial_processing_unit = "调度中心"
                    initial_status = "待处理"
                
                # 插入问题记录
                cursor.execute('''
                    INSERT INTO problems (
                        title, category, description, author, contact_info, department,
                        response_department, initial_processing_unit, initial_status,
                        processing_unit, processing_person, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    title, category, description, author, contact_info, department,
                    response_department, initial_processing_unit, initial_status,
                    initial_processing_unit, "", datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'), datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
                ))
                
                problem_id = cursor.lastrowid
                
                # 设置处理单位
                if response_department and response_department not in ["未定", "调度中心"]:
                    cursor.execute('''
                        UPDATE problems SET processing_unit = ?, status = ? WHERE id = ?
                    ''', (response_department, "已派发", problem_id))
                    
                    # 添加到部门关联表
                    cursor.execute('''
                        INSERT INTO problem_departments (problem_id, department, is_primary, assigned_by)
                        VALUES (?, ?, 1, ?)
                    ''', (problem_id, response_department, author))
                else:
                    # 添加到调度中心
                    cursor.execute('''
                        INSERT INTO problem_departments (problem_id, department, is_primary, assigned_by)
                        VALUES (?, ?, 1, ?)
                    ''', (problem_id, "调度中心", author))
                
                # 处理上传的文件
                if uploaded_files:
                    for uploaded_file in uploaded_files:
                        if uploaded_file is not None:
                            file_name = uploaded_file.name
                            file_size = uploaded_file.size
                            file_type = uploaded_file.type
                            
                            # 保存文件到本地
                            file_dir = "uploads"
                            if not os.path.exists(file_dir):
                                os.makedirs(file_dir)
                            
                            file_path = os.path.join(file_dir, f"{problem_id}_{file_name}")
                            with open(file_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            
                            # 记录文件信息
                            cursor.execute('''
                                INSERT INTO problem_files (problem_id, file_name, file_path, file_size, file_type)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (problem_id, file_name, file_path, file_size, file_type))
                
                conn.commit()
                return True, problem_id
                
        except Exception as e:
            print(f"保存问题失败: {e}")
            return False, str(e)
    
    def add_processing_record(self, problem_id, processor, measure, department=None, assigned_to=None):
        """添加处理记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO processing_records (problem_id, processor, measure, department, assigned_to, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (problem_id, processor, measure, department, assigned_to, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"添加处理记录失败: {e}")
            return False
    
    def get_processing_records(self, problem_id):
        """获取问题的处理记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM processing_records WHERE problem_id = ? ORDER BY created_at ASC
                ''', (problem_id,))
                
                records = []
                for record in cursor.fetchall():
                    try:
                        department = record['department'] if 'department' in record.keys() else None
                    except (KeyError, TypeError):
                        department = None
                    
                    try:
                        assigned_to = record['assigned_to'] if 'assigned_to' in record.keys() else None
                    except (KeyError, TypeError):
                        assigned_to = None
                    
                    records.append({
                        'id': record['id'],
                        'processor': record['processor'],
                        'measure': record['measure'],
                        'department': department,
                        'assigned_to': assigned_to,
                        'created_at': record['created_at']
                    })
                
                return records
                
        except Exception as e:
            print(f"获取处理记录失败: {e}")
            return []
    
    def get_department_processors(self, department):
        """获取部门的处理人"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, username, real_name, email, phone, department, role
                    FROM users WHERE department = ? AND role IN ('processor', 'manager', 'admin')
                    ORDER BY role DESC, real_name ASC
                ''', (department,))
                
                processors = []
                for row in cursor.fetchall():
                    processor = dict(zip([col[0] for col in cursor.description], row))
                    processors.append(processor)
                
                return processors
                
        except Exception as e:
            print(f"获取部门处理人失败: {e}")
            return []
    
    def get_all_departments(self):
        """获取所有部门"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT department FROM users 
                    WHERE department IS NOT NULL AND department != '' 
                    ORDER BY department
                ''')
                
                departments = [row[0] for row in cursor.fetchall()]
                return departments
                
        except Exception as e:
            print(f"获取部门列表失败: {e}")
            return []
    
    def assign_to_multiple_departments(self, problem_id, departments, operator):
        """分配问题到多个部门"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 清除现有分配
                cursor.execute('DELETE FROM problem_departments WHERE problem_id = ?', (problem_id,))
                
                # 添加新分配
                for i, dept in enumerate(departments):
                    is_primary = (i == 0)  # 第一个部门为主部门
                    cursor.execute('''
                        INSERT INTO problem_departments (problem_id, department, is_primary, assigned_by)
                        VALUES (?, ?, ?, ?)
                    ''', (problem_id, dept, is_primary, operator))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"分配部门失败: {e}")
            return False
    
    def get_work_order_statistics(self, user_info):
        """获取工单统计信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                user_department = user_info.get('department', '')
                user_role = user_info.get('role', '')
                
                # 根据用户角色和部门获取统计 - 使用与工单列表相同的权限逻辑
                if user_role == 'admin':
                    # 管理员可以看到所有统计
                    cursor.execute('''
                        SELECT p.*, 
                               COALESCE(p.processing_unit, '未分配') as processing_unit,
                               COALESCE(p.processing_person, '未分配') as processing_person,
                               (SELECT COUNT(*) FROM processing_records pr WHERE pr.problem_id = p.id) as processing_records_count
                        FROM problems p
                    ''')
                elif user_department == '调度中心':
                    # 调度中心用户：可以看到所有工单（因为调度中心需要全局视角）
                    cursor.execute('''
                        SELECT p.*, 
                               COALESCE(p.processing_unit, '未分配') as processing_unit,
                               COALESCE(p.processing_person, '未分配') as processing_person,
                               (SELECT COUNT(*) FROM processing_records pr WHERE pr.problem_id = p.id) as processing_records_count
                        FROM problems p
                    ''')
                else:
                    # 其他部门用户：可以看到与自己关联过的所有工单
                    # 包括：1. 自己部门创建的工单 2. 分配给自己部门的工单 3. 自己部门处理过的工单
                    cursor.execute('''
                        SELECT p.*, 
                               COALESCE(p.processing_unit, '未分配') as processing_unit,
                               COALESCE(p.processing_person, '未分配') as processing_person,
                               (SELECT COUNT(*) FROM processing_records pr WHERE pr.problem_id = p.id) as processing_records_count
                        FROM problems p
                        WHERE p.department = ? OR 
                              p.response_department = ? OR
                              EXISTS (SELECT 1 FROM problem_departments pd WHERE pd.problem_id = p.id AND pd.department = ?) OR
                              EXISTS (SELECT 1 FROM processing_records pr2 WHERE pr2.problem_id = p.id AND pr2.department = ?)
                    ''', (user_department, user_department, user_department, user_department))
                
                # 使用标准化的状态名称进行统计
                status_stats = {
                    '待处理': 0,
                    '已派发': 0,
                    '处理中': 0,
                    '已处理回复': 0,
                    '已办结': 0
                }
                
                for row in cursor.fetchall():
                    # 将行转换为字典格式
                    problem = dict(zip([col[0] for col in cursor.description], row))
                    
                    # 使用标准化方法计算状态
                    normalized_status = self._calculate_status_for_statistics(problem)
                    status_stats[normalized_status] += 1
                
                return status_stats
                
        except Exception as e:
            print(f"获取工单统计失败: {e}")
            # 返回默认的空统计
            return {
                '待处理': 0,
                '已派发': 0,
                '处理中': 0,
                '已处理回复': 0,
                '已办结': 0
            }
    
    def _calculate_status_for_statistics(self, problem):
        """计算问题的状态用于统计 - 使用与界面显示相同的逻辑"""
        try:
            status = problem.get('status', '')
            processing_unit = problem.get('processing_unit', '')
            is_processing = problem.get('is_processing', False)
            is_resolved = problem.get('is_resolved', False)
            processing_records_count = problem.get('processing_records_count', 0)
            
            # 使用与界面显示相同的状态判断逻辑
            if is_resolved:
                return '已办结'
            elif status == '已处理回复':
                return '已处理回复'
            elif is_processing or (processing_records_count > 0 and status != '待处理'):
                return '处理中'
            elif status == '已派发' or (processing_unit and processing_unit.strip() and status != '待处理'):
                return '已派发'
            else:
                return '待处理'
                
        except Exception as e:
            print(f"计算状态失败: {e}")
            return '待处理'
    
    def _fix_timezone_issues(self):
        """修复时区问题"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取当前北京时间
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                now_beijing = datetime.now(beijing_timezone)
                current_time = now_beijing.strftime('%Y-%m-%d %H:%M:%S')
                
                # 更新所有没有时区信息的时间字段
                cursor.execute('''
                    UPDATE problems SET created_at = ? WHERE created_at IS NULL OR created_at = ''
                ''', (current_time,))
                
                cursor.execute('''
                    UPDATE problems SET updated_at = ? WHERE updated_at IS NULL OR updated_at = ''
                ''', (current_time,))
                
                conn.commit()
                print("时区问题修复完成")
                
        except Exception as e:
            print(f"修复时区问题失败: {e}")
    
    def _ensure_problem_departments_structure(self):
        """确保problem_departments表结构正确"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='problem_departments'")
                if not cursor.fetchone():
                    cursor.execute('''
                        CREATE TABLE problem_departments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            problem_id INTEGER NOT NULL,
                            department TEXT NOT NULL,
                            is_primary BOOLEAN DEFAULT 0,
                            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            assigned_by TEXT,
                            FOREIGN KEY (problem_id) REFERENCES problems (id)
                        )
                    ''')
                    print("已创建problem_departments表")
                
                conn.commit()
                
        except Exception as e:
            print(f"确保表结构失败: {e}")
    
    def _migrate_to_multi_department(self):
        """迁移到多部门支持"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查problem_departments表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='problem_departments'")
                if not cursor.fetchone():
                    cursor.execute('''
                        CREATE TABLE problem_departments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            problem_id INTEGER NOT NULL,
                            department TEXT NOT NULL,
                            is_primary BOOLEAN DEFAULT 0,
                            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            assigned_by TEXT,
                            FOREIGN KEY (problem_id) REFERENCES problems (id)
                        )
                    ''')
                    print("已创建problem_departments表")
                
                # 检查processing_records表是否有department和assigned_to字段
                cursor.execute("PRAGMA table_info(processing_records)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'department' not in columns:
                    cursor.execute('ALTER TABLE processing_records ADD COLUMN department TEXT')
                    print("已添加department列到processing_records表")
                
                if 'assigned_to' not in columns:
                    cursor.execute('ALTER TABLE processing_records ADD COLUMN assigned_to TEXT')
                    print("已添加assigned_to列到processing_records表")
                
                # 检查problems表是否有必要的字段
                cursor.execute("PRAGMA table_info(problems)")
                problem_columns = [column[1] for column in cursor.fetchall()]
                
                # 添加缺失的字段
                if 'is_resolved' not in problem_columns:
                    cursor.execute('ALTER TABLE problems ADD COLUMN is_resolved BOOLEAN DEFAULT 0')
                    print("已添加is_resolved列到problems表")
                
                if 'is_processing' not in problem_columns:
                    cursor.execute('ALTER TABLE problems ADD COLUMN is_processing BOOLEAN DEFAULT 0')
                    print("已添加is_processing列到problems表")
                
                if 'processing_status' not in problem_columns:
                    cursor.execute('ALTER TABLE problems ADD COLUMN processing_status TEXT DEFAULT "待处理"')
                    print("已添加processing_status列到problems表")
                
                if 'response_department' not in problem_columns:
                    cursor.execute('ALTER TABLE problems ADD COLUMN response_department TEXT')
                    print("已添加response_department列到problems表")
                
                if 'priority' not in problem_columns:
                    cursor.execute('ALTER TABLE problems ADD COLUMN priority TEXT DEFAULT "普通"')
                    print("已添加priority列到problems表")
                
                conn.commit()
                # 数据库迁移完成
                
        except Exception as e:
            print(f"数据库迁移失败: {e}")

    # ==================== 基础数据查询方法 ====================
    
    def get_all_problems(self, filters=None):
        """获取所有问题"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT p.*, 
                           COALESCE(p.processing_unit, '未分配') as processing_unit,
                           COALESCE(p.processing_person, '未分配') as processing_person,
                           (SELECT COUNT(*) FROM processing_records pr WHERE pr.problem_id = p.id) as processing_records_count,
                           COALESCE(p.likes, 0) as likes,
                           COALESCE(p.dislikes, 0) as dislikes,
                           COALESCE(p.comments, 0) as comments,
                           COALESCE(p.views, 0) as views
                    FROM problems p
                '''
                
                params = []
                if filters:
                    conditions = []
                    if 'category' in filters:
                        conditions.append("p.category = ?")
                        params.append(filters['category'])
                    if 'status' in filters:
                        conditions.append("p.status = ?")
                        params.append(filters['status'])
                    if 'unit' in filters:  # 单位筛选
                        conditions.append("(p.processing_unit = ? OR p.department = ? OR p.response_department = ?)")
                        params.extend([filters['unit'], filters['unit'], filters['unit']])
                    if 'time_range' in filters:  # 时间范围筛选
                        beijing_timezone = pytz.timezone('Asia/Shanghai')
                        now = datetime.now(beijing_timezone)
                        
                        if filters['time_range'] == "今天":
                            start_date = now.strftime('%Y-%m-%d')
                            conditions.append("DATE(p.created_at) = ?")
                            params.append(start_date)
                        elif filters['time_range'] == "本周":
                            # 获取本周开始（周一）
                            days_since_monday = now.weekday()
                            week_start = now - timedelta(days=days_since_monday)
                            start_date = week_start.strftime('%Y-%m-%d')
                            conditions.append("DATE(p.created_at) >= ?")
                            params.append(start_date)
                        elif filters['time_range'] == "本月":
                            start_date = now.strftime('%Y-%m-01')
                            conditions.append("DATE(p.created_at) >= ?")
                            params.append(start_date)
                        elif filters['time_range'] == "最近30天":
                            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
                            conditions.append("DATE(p.created_at) >= ?")
                            params.append(start_date)
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY p.created_at DESC"
                
                cursor.execute(query, params)
                problems = []
                for row in cursor.fetchall():
                    problem = dict(zip([col[0] for col in cursor.description], row))
                    problem['is_new'] = self._is_problem_new(problem['created_at'])
                    problems.append(problem)
                
                return problems
                
        except Exception as e:
            print(f"获取问题列表失败: {e}")
            return []
    
    def get_problem_by_id(self, problem_id):
        """根据ID获取问题"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM problems WHERE id = ?
                ''', (problem_id,))
                
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
                
        except Exception as e:
            print(f"获取问题详情失败: {e}")
            return None
    
    def get_statistics(self):
        """获取统计数据"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 总问题数
                cursor.execute('SELECT COUNT(*) FROM problems')
                total_problems = cursor.fetchone()[0]
                
                # 今日新增
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                today = datetime.now(beijing_timezone).strftime('%Y-%m-%d')
                cursor.execute('SELECT COUNT(*) FROM problems WHERE DATE(created_at) = ?', (today,))
                today_new = cursor.fetchone()[0]
                
                # 本周新增
                week_start = (datetime.now(beijing_timezone) - timedelta(days=7)).strftime('%Y-%m-%d')
                cursor.execute('SELECT COUNT(*) FROM problems WHERE DATE(created_at) >= ?', (week_start,))
                week_new = cursor.fetchone()[0]
                
                # 分类统计
                cursor.execute('SELECT category, COUNT(*) FROM problems GROUP BY category')
                category_stats = dict(cursor.fetchall())
                
                # 部门统计
                cursor.execute('SELECT processing_unit, COUNT(*) FROM problems WHERE processing_unit IS NOT NULL GROUP BY processing_unit')
                department_stats = dict(cursor.fetchall())
                
                # 状态统计
                cursor.execute('SELECT status, COUNT(*) FROM problems GROUP BY status')
                status_stats = dict(cursor.fetchall())
                
                return {
                    'total_problems': total_problems,
                    'today_new': today_new,
                    'week_new': week_new,
                    'category_stats': category_stats,
                    'department_stats': department_stats,
                    'status_stats': status_stats
                }
                
        except Exception as e:
            print(f"获取统计数据失败: {e}")
            return {}
    
    def get_comments(self, problem_id):
        """获取问题的评论"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM comments WHERE problem_id = ? ORDER BY created_at ASC
                ''', (problem_id,))
                
                comments = []
                for row in cursor.fetchall():
                    comment = dict(zip([col[0] for col in cursor.description], row))
                    comments.append(comment)
                
                return comments
                
        except Exception as e:
            print(f"获取评论失败: {e}")
            return []
    
    def get_comment_replies(self, comment_id):
        """获取评论的回复"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM comment_replies WHERE comment_id = ? ORDER BY created_at ASC
                ''', (comment_id,))
                
                replies = []
                for row in cursor.fetchall():
                    reply = dict(zip([col[0] for col in cursor.description], row))
                    replies.append(reply)
                
                return replies
                
        except Exception as e:
            print(f"获取回复失败: {e}")
            return []
    
    def get_problem_files(self, problem_id):
        """获取问题的附件文件"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM problem_files WHERE problem_id = ? ORDER BY uploaded_at ASC
                ''', (problem_id,))
                
                files = []
                for row in cursor.fetchall():
                    file = dict(zip([col[0] for col in cursor.description], row))
                    files.append(file)
                
                return files
                
        except Exception as e:
            print(f"获取附件失败: {e}")
            return []
    
    def get_status_logs(self, problem_id):
        """获取问题的状态变更日志"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM status_logs WHERE problem_id = ? ORDER BY created_at ASC
                ''', (problem_id,))
                
                logs = []
                for row in cursor.fetchall():
                    log = dict(zip([col[0] for col in cursor.description], row))
                    logs.append(log)
                
                return logs
                
        except Exception as e:
            print(f"获取状态日志失败: {e}")
            return []
    
    def get_problem_departments(self, problem_id):
        """获取问题的部门分配"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM problem_departments WHERE problem_id = ? ORDER BY is_primary DESC, assigned_at ASC
                ''', (problem_id,))
                
                departments = []
                for row in cursor.fetchall():
                    dept = dict(zip([col[0] for col in cursor.description], row))
                    departments.append(dept)
                
                return departments
                
        except Exception as e:
            print(f"获取部门分配失败: {e}")
            return []
    
    def get_user_reaction(self, problem_id, user_id):
        """获取用户对问题的反应"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM reactions WHERE problem_id = ? AND user_id = ?
                ''', (problem_id, user_id))
                
                row = cursor.fetchone()
                if row:
                    return dict(zip([col[0] for col in cursor.description], row))
                return None
                
        except Exception as e:
            print(f"获取用户反应失败: {e}")
            return None
    
    # ==================== 数据操作方法 ====================
    
    def add_reaction(self, problem_id, user_id, reaction_type):
        """添加用户反应（点赞/踩）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查是否已有反应
                cursor.execute('''
                    SELECT id FROM reactions WHERE problem_id = ? AND user_id = ?
                ''', (problem_id, user_id))
                
                existing = cursor.fetchone()
                if existing:
                    # 更新现有反应
                    cursor.execute('''
                        UPDATE reactions SET reaction_type = ?, updated_at = ?
                        WHERE problem_id = ? AND user_id = ?
                    ''', (reaction_type, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'), problem_id, user_id))
                else:
                    # 创建新反应
                    cursor.execute('''
                        INSERT INTO reactions (problem_id, user_id, reaction_type, created_at)
                        VALUES (?, ?, ?, ?)
                    ''', (problem_id, user_id, reaction_type, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')))
                
                conn.commit()
                
                # 在主事务完成后，使用独立连接更新计数
                self._update_reaction_counts_delayed(problem_id)
                
                return True
                
        except Exception as e:
            print(f"添加反应失败: {e}")
            return False
    
    def add_comment(self, problem_id, author, content):
        """添加评论"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO comments (problem_id, author, content, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (problem_id, author, content, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')))
                
                # 更新问题的评论计数
                cursor.execute('''
                    UPDATE problems SET comments = comments + 1 WHERE id = ?
                ''', (problem_id,))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"添加评论失败: {e}")
            return False
    
    def add_comment_reply(self, comment_id, author, content):
        """添加评论回复"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO comment_replies (comment_id, author, content, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (comment_id, author, content, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"添加回复失败: {e}")
            return False
    
    def update_problem_status(self, problem_id, new_status, operator, comment):
        """更新问题状态"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 更新问题状态
                cursor.execute('''
                    UPDATE problems SET status = ?, updated_at = ? WHERE id = ?
                ''', (new_status, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'), problem_id))
                
                # 记录状态变更日志
                cursor.execute('''
                    INSERT INTO status_logs (problem_id, old_status, new_status, operator, comment, created_at)
                    VALUES (?, (SELECT status FROM problems WHERE id = ?), ?, ?, ?, ?)
                ''', (problem_id, problem_id, new_status, operator, comment, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"更新问题状态失败: {e}")
            return False
    
    def update_problem_processor(self, problem_id, processor, department=None):
        """更新问题处理人"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if department:
                    cursor.execute('''
                        UPDATE problems SET processing_person = ?, processing_unit = ?, updated_at = ?
                        WHERE id = ?
                    ''', (processor, department, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'), problem_id))
                else:
                    cursor.execute('''
                        UPDATE problems SET processing_person = ?, updated_at = ?
                        WHERE id = ?
                    ''', (processor, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'), problem_id))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"更新问题处理人失败: {e}")
            return False
    
    def delete_problem(self, problem_id, operator):
        """删除问题"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 记录删除操作
                cursor.execute('''
                    INSERT INTO status_logs (problem_id, old_status, new_status, operator, comment, created_at)
                    VALUES (?, (SELECT status FROM problems WHERE id = ?), '已删除', ?, '问题被删除', ?)
                ''', (problem_id, problem_id, operator, datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')))
                
                # 删除相关数据
                cursor.execute('DELETE FROM reactions WHERE problem_id = ?', (problem_id,))
                cursor.execute('DELETE FROM comment_replies WHERE comment_id IN (SELECT id FROM comments WHERE problem_id = ?)', (problem_id,))
                cursor.execute('DELETE FROM comments WHERE problem_id = ?', (problem_id,))
                cursor.execute('DELETE FROM processing_records WHERE problem_id = ?', (problem_id,))
                cursor.execute('DELETE FROM status_logs WHERE problem_id = ?', (problem_id,))
                cursor.execute('DELETE FROM problem_departments WHERE problem_id = ?', (problem_id,))
                cursor.execute('DELETE FROM problem_files WHERE problem_id = ?', (problem_id,))
                cursor.execute('DELETE FROM problems WHERE id = ?', (problem_id,))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"删除问题失败: {e}")
            return False
    
    def record_problem_view(self, problem_id, user_id):
        """记录问题查看 - 添加防重复机制"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查是否在短时间内已经记录过该用户的查看
                # 使用用户ID和问题ID的组合作为唯一标识
                view_key = f"{user_id}_{problem_id}"
                
                # 检查是否存在最近的查看记录（比如5分钟内）
                current_time = datetime.now(pytz.timezone('Asia/Shanghai'))
                five_minutes_ago = (current_time - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
                
                # 这里可以添加一个临时表来记录查看历史，但为了简化，我们直接更新
                # 如果需要在更细粒度控制，可以创建一个 problem_views 表
                
                # 更新浏览量（每次调用都增加，但通过前端会话状态控制频率）
                cursor.execute('''
                    UPDATE problems SET views = views + 1 WHERE id = ?
                ''', (problem_id,))
                
                conn.commit()
                print(f"✅ 记录问题 {problem_id} 的浏览量，用户: {user_id}")
                return True
                
        except Exception as e:
            print(f"记录查看失败: {e}")
            return False
    
    # ==================== 工单调度相关方法 ====================
    
    def update_work_orders_by_new_rules(self):
        """根据新规则更新工单"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取所有工单
                cursor.execute('SELECT id, response_department FROM problems')
                problems = cursor.fetchall()
                
                updated_count = 0
                for problem_id, response_department in problems:
                    if response_department and response_department not in ['未定', '调度中心']:
                        # 更新为已派发状态
                        cursor.execute('''
                            UPDATE problems SET status = '已派发', processing_unit = ? WHERE id = ?
                        ''', (response_department, problem_id))
                        updated_count += 1
                
                conn.commit()
                print(f"已更新 {updated_count} 个工单")
                return True
                
        except Exception as e:
            print(f"更新工单规则失败: {e}")
            return False
    
    def _format_problem_data(self, problem_dict):
        """格式化问题数据"""
        try:
            # 确保所有必要字段都存在
            formatted = {
                'id': problem_dict.get('id', 0),
                'title': problem_dict.get('title', ''),
                'category': problem_dict.get('category', ''),
                'status': problem_dict.get('status', ''),
                'processing_unit': problem_dict.get('processing_unit', ''),
                'processing_person': problem_dict.get('processing_person', ''),
                'created_at': problem_dict.get('created_at', ''),
                'author': problem_dict.get('author', ''),
                'description': problem_dict.get('description', ''),
                'response_department': problem_dict.get('response_department', ''),
                'processing_records_count': problem_dict.get('processing_records_count', 0)
            }
            
            return formatted
            
        except Exception as e:
            print(f"格式化问题数据失败: {e}")
            return problem_dict
    
    def _is_problem_new(self, created_at, hours=24):
        """判断问题是否为新问题"""
        try:
            if not created_at:
                return False
            
            # 解析创建时间
            if isinstance(created_at, str):
                # 如果时间字符串没有时区信息，假设为北京时间
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                try:
                    created_time = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                    # 将本地时间转换为北京时间
                    created_time = beijing_timezone.localize(created_time)
                except ValueError:
                    # 尝试其他时间格式
                    try:
                        created_time = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f')
                        created_time = beijing_timezone.localize(created_time)
                    except ValueError:
                        return False
            else:
                created_time = created_at
                # 如果datetime对象没有时区信息，假设为北京时间
                if created_time.tzinfo is None:
                    beijing_timezone = pytz.timezone('Asia/Shanghai')
                    created_time = beijing_timezone.localize(created_time)
            
            # 获取当前北京时间
            beijing_timezone = pytz.timezone('Asia/Shanghai')
            now = datetime.now(beijing_timezone)
            
            # 计算时间差
            time_diff = now - created_time
            return time_diff.total_seconds() < hours * 3600
            
        except Exception as e:
            print(f"判断问题新旧失败: {e}")
            return False
    
    def _update_reaction_counts(self, problem_id):
        """更新问题的反应计数"""
        try:
            # 使用独立的连接来更新计数，避免锁定问题
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            conn.row_factory = sqlite3.Row
            
            try:
                cursor = conn.cursor()
                
                # 统计点赞数
                cursor.execute('SELECT COUNT(*) FROM reactions WHERE problem_id = ? AND reaction_type = "like"', (problem_id,))
                likes = cursor.fetchone()[0]
                
                # 统计踩数
                cursor.execute('SELECT COUNT(*) FROM reactions WHERE problem_id = ? AND reaction_type = "dislike"', (problem_id,))
                dislikes = cursor.fetchone()[0]
                
                # 更新问题表
                cursor.execute('''
                    UPDATE problems SET likes = ?, dislikes = ? WHERE id = ?
                ''', (likes, dislikes, problem_id))
                
                conn.commit()
                print(f"✅ 成功更新问题 {problem_id} 的反应计数: 点赞={likes}, 踩={dislikes}")
                
            except Exception as e:
                print(f"❌ 更新反应计数时出错: {e}")
                conn.rollback()
            finally:
                conn.close()
                
        except Exception as e:
            print(f"❌ 连接数据库失败: {e}")
            # 如果更新失败，不阻塞主流程
            pass
    
    def _update_reaction_counts_delayed(self, problem_id):
        """延迟更新问题的反应计数"""
        try:
            # 使用独立的连接来更新计数，避免锁定问题
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            conn.row_factory = sqlite3.Row
            
            try:
                cursor = conn.cursor()
                
                # 统计点赞数
                cursor.execute('SELECT COUNT(*) FROM reactions WHERE problem_id = ? AND reaction_type = "like"', (problem_id,))
                likes = cursor.fetchone()[0]
                
                # 统计踩数
                cursor.execute('SELECT COUNT(*) FROM reactions WHERE problem_id = ? AND reaction_type = "dislike"', (problem_id,))
                dislikes = cursor.fetchone()[0]
                
                # 更新问题表
                cursor.execute('''
                    UPDATE problems SET likes = ?, dislikes = ? WHERE id = ?
                ''', (likes, dislikes, problem_id))
                
                conn.commit()
                print(f"✅ 成功更新问题 {problem_id} 的反应计数: 点赞={likes}, 踩={dislikes}")
                
            except Exception as e:
                print(f"❌ 更新反应计数时出错: {e}")
                conn.rollback()
            finally:
                conn.close()
                
        except Exception as e:
            print(f"❌ 连接数据库失败: {e}")
            # 如果更新失败，不阻塞主流程
            pass
    
    def _clean_content_thoroughly(self, content):
        """彻底清理内容中的HTML"""
        try:
            if not content:
                return ""
            
            # 使用BeautifulSoup清理HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            clean_text = soup.get_text()
            
            # 进一步清理特殊字符
            import re
            clean_text = re.sub(r'<[^>]*>', '', clean_text)  # 移除剩余HTML标签
            clean_text = re.sub(r'&[a-zA-Z]+;', '', clean_text)  # 移除HTML实体
            clean_text = re.sub(r'\s+', ' ', clean_text)  # 合并多个空格
            
            return clean_text.strip()
            
        except Exception as e:
            print(f"清理内容失败: {e}")
            # 如果BeautifulSoup不可用，使用正则表达式
            import re
            clean_text = re.sub(r'<[^>]*>', '', str(content))
            return clean_text.strip()

    def is_department_assigned_to_problem(self, problem_id, department):
        """检查部门是否被分配到此工单"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM problem_departments 
                    WHERE problem_id = ? AND department = ?
                ''', (problem_id, department))
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            print(f"检查部门分配失败: {e}")
            return False
    
    def check_all_collaborative_departments_processed(self, problem_id):
        """检查协同工单的所有部门是否都已处理"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取所有协同部门
                cursor.execute('''
                    SELECT department FROM problem_departments 
                    WHERE problem_id = ? AND department != '调度中心'
                    ORDER BY is_primary DESC, assigned_at ASC
                ''', (problem_id,))
                
                departments = [row[0] for row in cursor.fetchall()]
                
                if len(departments) <= 1:
                    return True  # 非协同工单或只有一个部门
                
                # 检查每个部门是否都有处理回复记录
                for dept in departments:
                    cursor.execute('''
                        SELECT COUNT(*) FROM processing_records 
                        WHERE problem_id = ? AND department = ? 
                        AND measure LIKE '%处理回复%'
                    ''', (problem_id, dept))
                    
                    if cursor.fetchone()[0] == 0:
                        return False  # 该部门还未处理回复
                
                return True  # 所有部门都已处理
                
        except Exception as e:
            print(f"检查协同部门处理状态失败: {e}")
            return False
    
    def get_next_collaborative_department(self, problem_id, current_processor):
        """获取协同工单的下一个待处理部门"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取当前处理人的部门
                cursor.execute('''
                    SELECT department FROM users WHERE real_name = ?
                ''', (current_processor,))
                
                current_dept_result = cursor.fetchone()
                if not current_dept_result:
                    return None
                
                current_dept = current_dept_result[0]
                
                # 获取所有协同部门（按优先级排序）
                cursor.execute('''
                    SELECT department FROM problem_departments 
                    WHERE problem_id = ? AND department != '调度中心'
                    ORDER BY is_primary DESC, assigned_at ASC
                ''', (problem_id,))
                
                departments = [row[0] for row in cursor.fetchall()]
                
                if len(departments) <= 1:
                    return None  # 非协同工单
                
                # 找到当前部门的索引
                try:
                    current_index = departments.index(current_dept)
                except ValueError:
                    return None
                
                # 查找下一个未处理的部门
                for i in range(current_index + 1, len(departments)):
                    next_dept = departments[i]
                    
                    # 检查该部门是否已处理回复
                    cursor.execute('''
                        SELECT COUNT(*) FROM processing_records 
                        WHERE problem_id = ? AND department = ? 
                        AND measure LIKE '%处理回复%'
                    ''', (problem_id, next_dept))
                    
                    if cursor.fetchone()[0] == 0:
                        return next_dept  # 找到下一个未处理的部门
                
                # 如果后面没有未处理的部门，检查前面的部门
                for i in range(current_index):
                    prev_dept = departments[i]
                    
                    cursor.execute('''
                        SELECT COUNT(*) FROM processing_records 
                        WHERE problem_id = ? AND department = ? 
                        AND measure LIKE '%处理回复%'
                    ''', (problem_id, prev_dept))
                    
                    if cursor.fetchone()[0] == 0:
                        return prev_dept  # 找到前面未处理的部门
                
                return None  # 所有部门都已处理
                
        except Exception as e:
            print(f"获取下一个协同部门失败: {e}")
            return None
    
    def is_department_collaborating_on_problem(self, problem_id, department):
        """检查部门是否协作处理此工单"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 检查处理记录中是否有协同处理记录
                cursor.execute('''
                    SELECT COUNT(*) FROM processing_records 
                    WHERE problem_id = ? AND department = ? AND measure LIKE '%协同%'
                ''', (problem_id, department))
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            print(f"检查部门协作失败: {e}")
            return False

# 创建全局数据库管理器实例
db = DatabaseManager()