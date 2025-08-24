import pandas as pd
import sqlite3
import streamlit as st
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class VerificationManager:
    """验证码管理器"""
    
    def __init__(self, db_path='feedback.db'):
        self.db_path = db_path
        self.init_verification_table()
    
    def init_verification_table(self):
        """初始化验证码表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建验证码表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS registration_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_id_suffix TEXT NOT NULL,  -- 工号牌后4位
                        phone_suffix TEXT NOT NULL,        -- 手机尾号后4位
                        verification_code TEXT UNIQUE NOT NULL,  -- 8位组合验证码
                        status TEXT DEFAULT 'active',      -- 状态：active/inactive
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        used_by TEXT,                      -- 使用此验证码的用户
                        used_at TIMESTAMP                  -- 使用时间
                    )
                ''')
                
                # 创建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_verification_code ON registration_codes(verification_code)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_employee_phone ON registration_codes(employee_id_suffix, phone_suffix)')
                
                conn.commit()
                logger.info("验证码表初始化完成")
                
        except Exception as e:
            logger.error(f"验证码表初始化失败: {e}")
            raise
    
    def import_from_excel(self, excel_file) -> bool:
        """从Excel文件导入验证码"""
        try:
            # 读取Excel文件
            df = pd.read_excel(excel_file)
            
            # 验证必要的列
            required_columns = ['工号牌后4位', '手机尾号后4位']
            if not all(col in df.columns for col in required_columns):
                st.error("Excel文件格式错误，需要包含：工号牌后4位、手机尾号后4位")
                return False
            
            # 清空现有数据
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM registration_codes')
                
                # 插入新数据
                for _, row in df.iterrows():
                    employee_suffix = str(row['工号牌后4位']).zfill(4)
                    phone_suffix = str(row['手机尾号后4位']).zfill(4)
                    verification_code = f"{employee_suffix}{phone_suffix}"
                    
                    cursor.execute('''
                        INSERT INTO registration_codes 
                        (employee_id_suffix, phone_suffix, verification_code)
                        VALUES (?, ?, ?)
                    ''', (employee_suffix, phone_suffix, verification_code))
                
                conn.commit()
                st.success(f"成功导入 {len(df)} 条验证码记录")
                return True
                
        except Exception as e:
            st.error(f"导入失败: {e}")
            return False
    
    def verify_code(self, verification_code: str) -> Optional[Dict]:
        """验证注册码"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, employee_id_suffix, phone_suffix, status, used_by
                    FROM registration_codes 
                    WHERE verification_code = ? AND status = 'active'
                ''', (verification_code,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'id': result[0],
                        'employee_id_suffix': result[1],
                        'phone_suffix': result[2],
                        'status': result[3],
                        'used_by': result[4]
                    }
                return None
                
        except Exception as e:
            logger.error(f"验证码验证失败: {e}")
            return None
    
    def mark_code_as_used(self, code_id: int, username: str):
        """标记验证码为已使用"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE registration_codes 
                    SET used_by = ?, used_at = CURRENT_TIMESTAMP, status = 'inactive'
                    WHERE id = ?
                ''', (username, code_id))
                conn.commit()
                
        except Exception as e:
            logger.error(f"标记验证码使用状态失败: {e}")
    
    def get_all_codes(self) -> List[Dict]:
        """获取所有验证码（管理员用）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, employee_id_suffix, phone_suffix, verification_code, 
                           status, used_by, used_at, created_at
                    FROM registration_codes 
                    ORDER BY created_at DESC
                ''')
                
                results = cursor.fetchall()
                return [
                    {
                        'id': row[0],
                        'employee_id_suffix': row[1],
                        'phone_suffix': row[2],
                        'verification_code': row[3],
                        'status': row[4],
                        'used_by': row[5],
                        'used_at': row[6],
                        'created_at': row[7]
                    }
                    for row in results
                ]
                
        except Exception as e:
            logger.error(f"获取验证码列表失败: {e}")
            return []
    
    def add_single_code(self, employee_suffix: str, phone_suffix: str) -> bool:
        """手动添加单个验证码"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                verification_code = f"{employee_suffix.zfill(4)}{phone_suffix.zfill(4)}"
                
                cursor.execute('''
                    INSERT INTO registration_codes 
                    (employee_id_suffix, phone_suffix, verification_code)
                    VALUES (?, ?, ?)
                ''', (employee_suffix.zfill(4), phone_suffix.zfill(4), verification_code))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"添加验证码失败: {e}")
            return False
