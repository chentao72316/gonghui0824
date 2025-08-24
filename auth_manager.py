import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging
import pytz
import streamlit as st

logger = logging.getLogger(__name__)

class AuthManager:
    """用户认证和权限管理器"""
    
    def __init__(self, db_path='feedback.db'):
        self.db_path = db_path
        self.init_auth_tables()
        self.create_default_users()
    
    def init_auth_tables(self):
        """初始化认证相关表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查用户表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                if cursor.fetchone():
                    # 检查是否有status列
                    cursor.execute("PRAGMA table_info(users)")
                    columns = [column[1] for column in cursor.fetchall()]
                    if 'status' not in columns:
                        # 添加status列
                        cursor.execute('ALTER TABLE users ADD COLUMN status TEXT DEFAULT "active"')
 
                else:
                    # 创建用户表
                    cursor.execute('''
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL,
                            real_name TEXT NOT NULL,
                            email TEXT,
                            phone TEXT,
                            department TEXT,
                            role TEXT NOT NULL CHECK (role IN ('user', 'processor', 'manager', 'admin')),
                            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_login TIMESTAMP,
                            created_by INTEGER,
                            FOREIGN KEY (created_by) REFERENCES users (id)
                        )
                    ''')

                
                # 检查用户会话表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_sessions'")
                if not cursor.fetchone():
                    cursor.execute('''
                        CREATE TABLE user_sessions (
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

                
                conn.commit()
                logger.info("认证表初始化完成")
                
        except Exception as e:
            logger.error(f"认证表初始化失败: {e}")
            raise
    
    def hash_password(self, password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        return self.hash_password(password) == password_hash
    
    def create_default_users(self):
        """创建默认测试用户"""
        default_users = [
            {
                'username': 'admin',
                'password': 'admin123',
                'real_name': '系统管理员',
                'email': 'admin@example.com',
                'department': 'IT部门',
                'role': 'admin'
            },
            {
                'username': 'diaodu1',
                'password': 'diaodu123',
                'real_name': '调度中心处理人',
                'email': 'diaodu@example.com',
                'department': '调度中心',
                'role': 'admin'
            },
            {
                'username': 'manager',
                'password': 'manager123',
                'real_name': '张经理',
                'email': 'manager@example.com',
                'department': '运营部',
                'role': 'manager'
            },
            {
                'username': 'processor',
                'password': 'processor123',
                'real_name': '李处理员',
                'email': 'processor@example.com',
                'department': '客服部',
                'role': 'processor'
            },
            {
                'username': 'user',
                'password': 'user123',
                'real_name': '王用户',
                'email': 'user@example.com',
                'department': '市场部',
                'role': 'user'
            }
        ]
        
        for user_data in default_users:
            self.create_user_if_not_exists(user_data)
    
    def create_user_if_not_exists(self, user_data: Dict):
        """如果用户不存在则创建"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查用户是否已存在
                cursor.execute('SELECT id FROM users WHERE username = ?', (user_data['username'],))
                if cursor.fetchone():
                    return
                
                # 创建新用户
                password_hash = self.hash_password(user_data['password'])
                cursor.execute('''
                    INSERT INTO users (username, password_hash, real_name, email, department, role)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    user_data['username'],
                    password_hash,
                    user_data['real_name'],
                    user_data['email'],
                    user_data['department'],
                    user_data['role']
                ))
                
                conn.commit()
                logger.info(f"创建默认用户: {user_data['username']}")
                
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """用户认证"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 首先检查表结构
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                # 获取表结构信息
                
                # 构建查询语句，只查询存在的列
                if 'status' in columns:
                    query = '''
                        SELECT id, username, password_hash, real_name, email, phone, department, role, status
                        FROM users WHERE username = ?
                    '''
                else:
                    query = '''
                        SELECT id, username, password_hash, real_name, email, phone, department, role
                        FROM users WHERE username = ?
                    '''
                
                cursor.execute(query, (username,))
                user = cursor.fetchone()
                
                if not user:
                    return None
                
                # 构建用户字典
                if 'status' in columns:
                    user_dict = {
                        'id': user[0],
                        'username': user[1],
                        'password_hash': user[2],
                        'real_name': user[3],
                        'email': user[4],
                        'phone': user[5],
                        'department': user[6],
                        'role': user[7],
                        'status': user[8]
                    }
                else:
                    user_dict = {
                        'id': user[0],
                        'username': user[1],
                        'password_hash': user[2],
                        'real_name': user[3],
                        'email': user[4],
                        'phone': user[5],
                        'department': user[6],
                        'role': user[7],
                        'status': 'active'  # 默认状态
                    }
                
                # 检查用户状态
                if user_dict.get('status') and user_dict['status'] != 'active':
                    return None
                
                # 验证密码
                input_password_hash = self.hash_password(password)
                
                if input_password_hash != user_dict['password_hash']:
                    return None
                
                # 更新最后登录时间
                try:
                    # 获取当前北京时间
                    beijing_timezone = pytz.timezone('Asia/Shanghai')
                    now_beijing = datetime.now(beijing_timezone)
                    current_time = now_beijing.strftime('%Y-%m-%d %H:%M:%S')
                    
                    cursor.execute('''
                        UPDATE users SET last_login = ? WHERE id = ?
                    ''', (current_time, user_dict['id'],))
                    conn.commit()
                except Exception as e:
                    pass
                
                return user_dict
                
        except Exception as e:
            logger.error(f"用户认证失败: {e}")
            return None
    
    def create_session(self, user_id: int, ip_address: str = None, user_agent: str = None) -> Optional[str]:
        """创建用户会话"""
        try:
            session_token = secrets.token_urlsafe(32)
            
            # 使用北京时间
            beijing_timezone = pytz.timezone('Asia/Shanghai')
            now_beijing = datetime.now(beijing_timezone)
            expires_at = now_beijing + timedelta(hours=24)
            
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查用户是否存在
                cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                if not cursor.fetchone():
                    return None
                
                # 清理过期会话
                # 获取当前北京时间
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                now_beijing = datetime.now(beijing_timezone)
                current_time = now_beijing.strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute("DELETE FROM user_sessions WHERE expires_at < ?", (current_time,))
                
                # 创建新会话
                cursor.execute('''
                    INSERT INTO user_sessions (user_id, session_token, expires_at, ip_address, user_agent)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, session_token, expires_at, ip_address, user_agent))
                
                conn.commit()
                return session_token
                
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return None
    
    def validate_session(self, session_token: str) -> Optional[Dict]:
        """验证会话"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查表结构
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                
                # 构建查询语句
                if 'status' in columns:
                    query = '''
                        SELECT u.id, u.username, u.real_name, u.email, u.phone, u.department, u.role, u.status
                        FROM users u
                        JOIN user_sessions s ON u.id = s.user_id
                        WHERE s.session_token = ? AND s.expires_at > ?
                    '''
                else:
                    query = '''
                        SELECT u.id, u.username, u.real_name, u.email, u.phone, u.department, u.role
                        FROM users u
                        JOIN user_sessions s ON u.id = s.user_id
                        WHERE s.session_token = ? AND s.expires_at > ?
                    '''
                
                # 获取当前北京时间
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                now_beijing = datetime.now(beijing_timezone)
                current_time = now_beijing.strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute(query, (session_token, current_time))
                user = cursor.fetchone()
                
                if not user:
                    return None
                
                # 构建用户字典
                if 'status' in columns:
                    return {
                        'id': user[0],
                        'username': user[1],
                        'real_name': user[2],
                        'email': user[3],
                        'phone': user[4],
                        'department': user[5],
                        'role': user[6],
                        'status': user[7]
                    }
                else:
                    return {
                        'id': user[0],
                        'username': user[1],
                        'real_name': user[2],
                        'email': user[3],
                        'phone': user[4],
                        'department': user[5],
                        'role': user[6],
                        'status': 'active'
                    }
                
        except Exception as e:
            logger.error(f"验证会话失败: {e}")
            return None
    
    def check_session(self) -> bool:
        """检查当前会话是否有效"""
        session_token = st.session_state.get('session_token')
        if not session_token:
            return False
        
        user_info = self.validate_session(session_token)
        if user_info:
            # 更新session_state中的用户信息
            st.session_state.user_info = user_info
            st.session_state.user_id = user_info['id']
            st.session_state.user_name = user_info['real_name']
            st.session_state.user_role = user_info['role']
            return True
        
        return False
    
    def logout(self, session_token: str) -> bool:
        """用户登出"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_sessions WHERE session_token = ?', (session_token,))
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"登出失败: {e}")
            return False
    
    def check_permission(self, user_role: str, required_permission: str) -> bool:
        """检查用户权限"""
        permission_hierarchy = {
            'user': ['view_problems', 'create_problems', 'comment', 'like'],
            'processor': ['view_problems', 'create_problems', 'comment', 'like', 'process_problems', 'update_status', 'add_records'],
            'manager': ['view_problems', 'create_problems', 'comment', 'like', 'process_problems', 'update_status', 'add_records', 'assign_problems', 'export_data', 'view_users'],
            'admin': ['view_problems', 'create_problems', 'comment', 'like', 'process_problems', 'update_status', 'add_records', 'assign_problems', 'export_data', 'view_users', 'manage_users', 'system_config', 'delete_problems']
        }
        
        user_permissions = permission_hierarchy.get(user_role, [])
        return required_permission in user_permissions
    
    def get_all_users(self) -> List[Dict]:
        """获取所有用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, username, real_name, email, department, role, status, created_at, last_login
                    FROM users ORDER BY created_at DESC
                ''')
                
                users = []
                for row in cursor.fetchall():
                    users.append({
                        'id': row[0],
                        'username': row[1],
                        'real_name': row[2],
                        'email': row[3],
                        'department': row[4],
                        'role': row[5],
                        'status': row[6],
                        'created_at': row[7],
                        'last_login': row[8]
                    })
                
                return users
                
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []
    
    def create_user(self, user_data: Dict, created_by: int) -> bool:
        """创建新用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查用户名是否已存在
                cursor.execute('SELECT id FROM users WHERE username = ?', (user_data['username'],))
                if cursor.fetchone():
                    logger.warning(f"用户名已存在: {user_data['username']}")
                    return False
                
                password_hash = self.hash_password(user_data['password'])
                
                cursor.execute('''
                    INSERT INTO users (username, password_hash, real_name, email, phone, department, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_data['username'],
                    password_hash,
                    user_data['real_name'],
                    user_data.get('email'),
                    user_data.get('phone'),
                    user_data.get('department'),
                    user_data['role']
                ))
                
                conn.commit()
                logger.info(f"用户创建成功: {user_data['username']}")
                return True
                
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
            return False
    
    def update_user(self, user_id: int, user_data: Dict) -> bool:
        """更新用户信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                update_fields = []
                params = []
                
                for field in ['real_name', 'email', 'phone', 'department', 'role', 'status']:
                    if field in user_data:
                        update_fields.append(f"{field} = ?")
                        params.append(user_data[field])
                
                if update_fields:
                    params.append(user_id)
                    cursor.execute(f'''
                        UPDATE users SET {', '.join(update_fields)} WHERE id = ?
                    ''', params)
                    
                    conn.commit()
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"更新用户失败: {e}")
            return False
    
    def update_user_profile(self, user_id: int, user_data: Dict) -> bool:
        """更新用户个人信息（包括密码）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                update_fields = []
                params = []
                
                # 处理基本信息字段
                for field in ['real_name', 'email', 'phone', 'department']:
                    if field in user_data:
                        update_fields.append(f"{field} = ?")
                        params.append(user_data[field])
                
                # 处理密码更新
                if 'password' in user_data:
                    password_hash = self.hash_password(user_data['password'])
                    update_fields.append("password_hash = ?")
                    params.append(password_hash)
                
                if update_fields:
                    params.append(user_id)
                    cursor.execute(f'''
                        UPDATE users SET {', '.join(update_fields)} WHERE id = ?
                    ''', params)
                    
                    conn.commit()
                    logger.info(f"用户个人信息更新成功: {user_id}")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"更新用户个人信息失败: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """删除用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查用户是否存在
                cursor.execute('SELECT id, username FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                if not user:
                    logger.warning(f"用户不存在: {user_id}")
                    return False
                
                # 删除用户的会话
                cursor.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
                
                # 删除用户
                cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
                
                conn.commit()
                logger.info(f"用户删除成功: {user[1]} (ID: {user_id})")
                return True
                
        except Exception as e:
            logger.error(f"删除用户失败: {e}")
            return False

# 创建全局认证管理器实例
# 使用简单的单例模式
_auth_manager_instance = None

def get_auth_manager():
    global _auth_manager_instance
    if _auth_manager_instance is None:
        _auth_manager_instance = AuthManager()
    return _auth_manager_instance

auth_manager = get_auth_manager() 