import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import re
import html
from bs4 import BeautifulSoup
import pytz # Added for timezone handling
from typing import List, Dict, Optional

# 导入数据库管理器
from db_manager import db

# 导入认证管理器
from auth_manager import auth_manager

# 导入权限控制
from permission_control import require_role, render_navigation_sidebar

# 导入导出管理器
from export_manager import export_manager

# 配置页面
st.set_page_config(
    page_title="工单调度",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
        padding: 1rem;
        background: linear-gradient(90deg, #f0f8ff, #e6f3ff);
        border-radius: 10px;
    }
    
    .metric-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        margin: 10px 0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    .metric-number {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 5px;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #666;
    }
    
    .work-order-detail {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    .work-order-operation {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 20px;
        margin: 10px 0;
    }
    
    .status-tag {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    
    .status-pending { background-color: #fff3cd; color: #856404; }
    .status-assigned { background-color: #d1ecf1; color: #0c5460; }
    .status-processing { background-color: #d4edda; color: #155724; }
    .status-replied { background-color: #e2e3e5; color: #383d41; }
    .status-resolved { background-color: #f8d7da; color: #721c24; }
</style>
""", unsafe_allow_html=True)

# 定义工单状态常量
WORK_ORDER_STATUS = {
    'PENDING': '待处理',
    'ASSIGNED': '已派发',
    'PROCESSING': '处理中',
    'REPLIED': '已处理回复',
    'RESOLVED': '已办结'
}

# 定义工单流转阶段常量
WORK_ORDER_STAGES = {
    'DISPATCH_CENTER': '调度中心',
    'DEPARTMENT_PROCESSING': '部门处理',
    'DISPATCH_CENTER_REVIEW': '调度中心确认'
}

def check_user_permission():
    """检查用户是否有权限访问工单调度页面"""
    user_info = st.session_state.get('user_info')
    if not user_info:
        st.error("请先登录！")
        st.stop()
    
    # 检查用户角色权限 - user角色不能访问工单调度界面
    user_role = user_info.get('role', '')
    if user_role == 'user':
        st.error("您没有权限访问工单调度页面！")
        st.stop()
    
    return user_info

def get_filtered_work_orders(user_info: Dict, status_filter: str = "全部", category_filter: str = "全部分类", department_filter: str = "全部部门") -> List[Dict]:
    """根据筛选条件获取工单列表 - 显示与自己关联过的所有工单"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            user_role = user_info['role']
            user_name = user_info['real_name']
            user_department = user_info.get('department', '')
            
            # 构建基础查询
            query = '''
                SELECT p.*, 
                       COUNT(pr.id) as processing_records_count
                FROM problems p
                LEFT JOIN processing_records pr ON p.id = pr.problem_id
                WHERE 1=1
            '''
            params = []
            
            # 检查字段是否存在
            cursor.execute("PRAGMA table_info(problems)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # 根据用户角色和部门过滤 - 显示与自己关联过的所有工单
            if user_role == 'admin':
                # admin可以看到所有工单
                pass
            else:
                # 根据用户部门进行权限过滤 - 支持多部门关联
                if user_department == '调度中心':
                    # 调度中心用户：可以看到所有工单（因为调度中心需要全局视角）
                    pass
                else:
                    # 其他部门用户：可以看到与自己关联过的所有工单
                    # 包括：1. 自己部门创建的工单 2. 分配给自己部门的工单 3. 自己部门处理过的工单
                    query += ''' AND (
                        p.department = ? OR 
                        p.response_department = ? OR
                        EXISTS (SELECT 1 FROM problem_departments pd WHERE pd.problem_id = p.id AND pd.department = ?) OR
                        EXISTS (SELECT 1 FROM processing_records pr2 WHERE pr2.problem_id = p.id AND pr2.department = ?)
                    )'''
                    params.extend([user_department, user_department, user_department, user_department])
            
            # 状态筛选
            if status_filter != "全部状态" and status_filter != "全部":
                # 根据状态筛选，需要考虑处理记录
                if status_filter == "待处理":
                    # 检查字段是否存在
                    conditions = ["p.status = '待处理'"]
                    if 'is_processing' in columns:
                        conditions.append("p.is_processing = 0")
                    if 'is_resolved' in columns:
                        conditions.append("p.is_resolved = 0")
                    conditions.append("NOT EXISTS (SELECT 1 FROM processing_records pr2 WHERE pr2.problem_id = p.id)")
                    query += " AND (" + " AND ".join(conditions) + ")"
                elif status_filter == "已派发":
                    query += " AND p.status = '已派发'"
                elif status_filter == "处理中":
                    # 检查字段是否存在
                    conditions = []
                    if 'is_processing' in columns:
                        conditions.append("p.is_processing = 1")
                    conditions.append("EXISTS (SELECT 1 FROM processing_records pr2 WHERE pr2.problem_id = p.id)")
                    conditions.append("p.status != '已处理回复'")
                    if 'is_resolved' in columns:
                        conditions.append("p.is_resolved = 0")
                    query += " AND (" + " OR ".join(conditions[:2]) + ") AND " + " AND ".join(conditions[2:]) if len(conditions) > 2 else " AND (" + " OR ".join(conditions) + ")"
                elif status_filter == "已处理回复":
                    query += " AND p.status = '已处理回复'"
                elif status_filter == "已办结":
                    if 'is_resolved' in columns:
                        query += " AND p.is_resolved = 1"
                    else:
                        query += " AND p.status = '已办结'"
                else:
                    query += " AND p.status = ?"
                    params.append(status_filter)
            
            # 分类筛选
            if category_filter != "全部分类":
                query += " AND p.category = ?"
                params.append(category_filter)
            
            # 部门筛选
            if department_filter != "全部部门":
                query += " AND p.department = ?"
                params.append(department_filter)
            
            query += " GROUP BY p.id ORDER BY p.created_at DESC"
            
            cursor.execute(query, params)
            problems = []
            for row in cursor.fetchall():
                # 不使用_format_problem_data，直接转换为字典并保留原始字段
                problem_dict = dict(row)
                
                # 添加格式化的时间显示
                try:
                    if problem_dict.get('created_at'):
                        created_time = datetime.strptime(str(problem_dict['created_at']), '%Y-%m-%d %H:%M:%S')
                        problem_dict['formatted_created_at'] = created_time.strftime('%Y年%m月%d日 %H:%M')
                    else:
                        problem_dict['formatted_created_at'] = problem_dict.get('created_at', '未设置')
                except:
                    problem_dict['formatted_created_at'] = problem_dict.get('created_at', '未设置')
                
                # 添加工单号
                problem_dict['work_order'] = f"WT{str(problem_dict['id']).zfill(5)}"
                
                problems.append(problem_dict)
            
            return problems
            
    except Exception as e:
        st.error(f"获取工单列表失败: {e}")
        return []

def get_previous_department(problem_id):
    """获取工单的上一流程部门 - 考虑时区修正"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取处理记录，按时间排序
            cursor.execute("""
                SELECT department, measure, created_at
                FROM processing_records 
                WHERE problem_id = ? 
                ORDER BY created_at
            """, (problem_id,))
            
            records = cursor.fetchall()
            
            if len(records) >= 2:
                # 创建带时区修正的记录列表
                corrected_records = []
                for record in records:
                    department, measure, created_at = record
                    
                    if "驳回" in measure and created_at:
                        try:
                            # 驳回记录：UTC时间转换为北京时间（+8小时）
                            parsed_time = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                            corrected_time = parsed_time + timedelta(hours=8)
                        except:
                            corrected_time = created_at
                    else:
                        corrected_time = created_at
                    
                    corrected_records.append((department, measure, corrected_time))
                
                # 按修正后的时间排序
                corrected_records.sort(key=lambda x: x[2] if isinstance(x[2], datetime) else datetime.strptime(str(x[2]), '%Y-%m-%d %H:%M:%S'))
                
                # 倒数第二条记录应该是上一流程部门
                if len(corrected_records) >= 2:
                    previous_record = corrected_records[-2]
                    return previous_record[0]  # department字段
                else:
                    return "无"
            else:
                return "无"
    except Exception as e:
        print(f"获取上一流程部门失败: {e}")
        return "无"

def is_collaboration_work_order(problem_id):
    """判断是否为真正的协作工单 - 简化版本"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # 直接通过problem_departments表判断是否为协同工单
            cursor.execute("""
                SELECT COUNT(*) as dept_count
                FROM problem_departments 
                WHERE problem_id = ? AND department != '调度中心'
            """, (problem_id,))
            
            result = cursor.fetchone()
            if result:
                # 如果关联的部门数量大于1，则为协同工单
                return result[0] > 1
            
            return False
    except Exception as e:
        print(f"判断协作工单失败: {e}")
        return False

def get_operable_work_orders(user_info: Dict) -> List[Dict]:
    """获取用户可操作的工单列表 - 用于工单操作区域显示"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            user_role = user_info['role']
            user_department = user_info.get('department', '')
            
            # 构建查询
            query = '''
                SELECT p.*, 
                       COUNT(pr.id) as processing_records_count
                FROM problems p
                LEFT JOIN processing_records pr ON p.id = pr.problem_id
                WHERE 1=1
            '''
            params = []
            
            # 根据新规则过滤可操作的工单 - 支持多部门
            # 首先排除已办结的工单（除非是admin且需要重新开启）
            # 检查字段是否存在
            cursor.execute("PRAGMA table_info(problems)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'is_resolved' in columns:
                query += ' AND p.is_resolved = 0'
            
            if user_role == 'admin':
                if user_department == '调度中心':
                    # 归属调度中心的admin：显示以下工单：
                    # 1. 待处理状态的工单
                    # 2. 当前受理部门为调度中心的工单
                    # 3. 在多部门关联中包含调度中心的工单
                    # 4. 已处理回复状态且所有协同部门都已处理的协同工单
                    
                    # 构建查询条件，检查字段是否存在
                    conditions = []
                    
                    if 'is_processing' in columns and 'is_resolved' in columns:
                        conditions.append("(p.status = '待处理' AND p.is_processing = 0 AND p.is_resolved = 0 AND NOT EXISTS (SELECT 1 FROM processing_records pr2 WHERE pr2.problem_id = p.id))")
                    
                    conditions.append("p.processing_unit = '调度中心'")
                    conditions.append("EXISTS (SELECT 1 FROM problem_departments pd WHERE pd.problem_id = p.id AND pd.department = '调度中心')")
                    
                    if 'is_resolved' in columns:
                        conditions.append("(p.status = '已处理回复' AND EXISTS (SELECT 1 FROM problem_departments pd2 WHERE pd2.problem_id = p.id AND pd2.department != '调度中心') AND NOT EXISTS (SELECT 1 FROM problem_departments pd3 WHERE pd3.problem_id = p.id AND pd3.department != '调度中心' AND NOT EXISTS (SELECT 1 FROM processing_records pr3 WHERE pr3.problem_id = p.id AND pr3.department = pd3.department AND pr3.measure LIKE '%处理回复%')))")
                    
                    query += ' AND (' + ' OR '.join(conditions) + ')'
                else:
                    # 其他部门的admin：仅显示当前受理部门为自己部门的工单，或者在多部门关联中包含自己部门的工单
                    query += ''' AND (
                        p.processing_unit = ? OR
                        EXISTS (SELECT 1 FROM problem_departments pd WHERE pd.problem_id = p.id AND pd.department = ?)
                    )'''
                    params.extend([user_department, user_department])
            else:
                # processor和manager角色
                if user_department == '调度中心':
                    # 归属调度中心的processor、manager：显示以下工单：
                    # 1. 待处理状态的工单
                    # 2. 当前受理部门为调度中心的工单
                    # 3. 在多部门关联中包含调度中心的工单
                    # 4. 已处理回复状态且所有协同部门都已处理的协同工单
                    
                    # 构建查询条件，检查字段是否存在
                    conditions = []
                    
                    if 'is_processing' in columns and 'is_resolved' in columns:
                        conditions.append("(p.status = '待处理' AND p.is_processing = 0 AND p.is_resolved = 0 AND NOT EXISTS (SELECT 1 FROM processing_records pr2 WHERE pr2.problem_id = p.id))")
                    
                    conditions.append("p.processing_unit = '调度中心'")
                    conditions.append("EXISTS (SELECT 1 FROM problem_departments pd WHERE pd.problem_id = p.id AND pd.department = '调度中心')")
                    
                    if 'is_resolved' in columns:
                        conditions.append("(p.status = '已处理回复' AND EXISTS (SELECT 1 FROM problem_departments pd2 WHERE pd2.problem_id = p.id AND pd2.department != '调度中心') AND NOT EXISTS (SELECT 1 FROM problem_departments pd3 WHERE pd3.problem_id = p.id AND pd3.department != '调度中心' AND NOT EXISTS (SELECT 1 FROM processing_records pr3 WHERE pr3.problem_id = p.id AND pr3.department = pd3.department AND pr3.measure LIKE '%处理回复%')))")
                    
                    query += ' AND (' + ' OR '.join(conditions) + ')'
                else:
                    # 其他部门的processor、manager：只能操作当前受理部门为自己部门的工单，或者在多部门关联中包含自己部门的工单
                    query += ''' AND (
                        p.processing_unit = ? OR
                        EXISTS (SELECT 1 FROM problem_departments pd WHERE pd.problem_id = p.id AND pd.department = ?)
                    )'''
                    params.extend([user_department, user_department])
            
            query += " GROUP BY p.id ORDER BY p.created_at DESC"
            
            cursor.execute(query, params)
            problems = []
            for row in cursor.fetchall():
                # 将sqlite3.Row对象转换为字典
                problem_dict = dict(row)
                problems.append(db._format_problem_data(problem_dict))
            
            return problems
            
    except Exception as e:
        st.error(f"获取可操作工单失败: {e}")
        return []

def get_all_categories() -> List[str]:
    """获取所有分类"""
    return [
        "发展经营类", "企业文化建设类", "后勤服务类", "职工教育成长类", 
        "生活福利类", "劳动保护类", "薪酬晋升类", "民主管理类", "其他方面"
    ]

def get_all_departments() -> List[str]:
    """获取所有部门"""
    return [
        "网络部", "综合部", "人力部", "市场部", "集客部", "全业务支撑中心", 
        "客体部", "党建部", "财务部", "工会", "纪委办",
        "船山", "射洪", "蓬溪", "大英", "安居", "调度中心"
    ]

def get_all_statuses() -> List[str]:
    """获取所有状态"""
    return ["全部状态", "待处理", "已派发", "处理中", "已处理回复", "已办结"]

# 工单操作函数
def is_rejected_work_order(problem_id: int) -> bool:
    """检查工单是否为驳回工单"""
    try:
        processing_records = db.get_processing_records(problem_id)
        if processing_records:
            # 查找最新的驳回记录
            for record in reversed(processing_records):
                measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
                if "工单被驳回" in measure or "驳回" in measure:
                    return True
        return False
    except Exception as e:
        print(f"检查驳回工单失败: {e}")
        return False

def assign_work_order(problem_id: int, assigned_departments: List[str], assigned_persons: List[str], operator: str, dispatch_comments: str = "") -> bool:
    """派发工单 - 支持多部门"""
    try:
        # 更新工单状态为已派发
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['ASSIGNED'], operator, f"工单已派发，派发意见：{dispatch_comments}")
        
        if success:
            # 使用新的多部门派发功能
            if assigned_departments:
                db.assign_to_multiple_departments(problem_id, assigned_departments, operator)
                
                # 更新工单处理人（取第一个部门的第一个处理人作为主要处理人）
                if assigned_persons:
                    primary_person = assigned_persons[0]
                    db.update_problem_processor(problem_id, primary_person)
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单派发，处理部门：{', '.join(assigned_departments)}，处理人：{', '.join(assigned_persons)}，派发意见：{dispatch_comments}",
                department=assigned_departments[0] if assigned_departments else None,
                assigned_to=assigned_persons[0] if assigned_persons else None
            )
            return True
        return False
    except Exception as e:
        st.error(f"派发工单失败: {e}")
        return False

def dispatch_from_center(problem_id: int, assigned_departments: List[str], assigned_persons: List[str], operator: str, dispatch_comments: str = "") -> bool:
    """调度中心转派工单 - 支持多部门"""
    try:
        # 更新工单状态为已派发
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['ASSIGNED'], operator, f"调度中心转派，转派意见：{dispatch_comments}")
        
        if success:
            # 使用新的多部门派发功能
            if assigned_departments:
                db.assign_to_multiple_departments(problem_id, assigned_departments, operator)
                
                # 更新工单处理人和处理部门（取第一个部门的第一个处理人作为主要处理人）
                if assigned_persons:
                    primary_person = assigned_persons[0]
                    primary_department = assigned_departments[0]
                    db.update_problem_processor(problem_id, primary_person, primary_department)
            
            # 添加处理记录 - 正确设置流转信息
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"调度中心转派，转派部门：{', '.join(assigned_departments)}，处理人：{', '.join(assigned_persons)}，转派意见：{dispatch_comments}",
                department="调度中心",  # 当前处理部门是调度中心
                assigned_to=assigned_persons[0] if assigned_persons else None  # 流转至的处理人
            )
            return True
        return False
    except Exception as e:
        st.error(f"调度中心转派失败: {e}")
        return False

def accept_work_order(problem_id: int, processor: str, processing_comments: str = "") -> bool:
    """接单处理 - 按照新业务规则：从已派发或处理中状态调整为处理中状态，当前处理部门不变"""
    try:
        # 获取用户信息
        user_department = st.session_state.user_info.get('department', '')
        
        # 更新工单状态为处理中
        success = db.update_problem_status(problem_id, "处理中", processor, f"已接单开始处理，处理意见：{processing_comments}")
        
        if success:
            # 更新工单状态字段，设置当前处理部门和处理人
            current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE problems 
                    SET is_processing = 1, 
                        processing_person = ?,
                        processing_unit = ?,
                        processing_status = '处理中',
                        updated_at = ?
                    WHERE id = ?
                ''', (processor, user_department, current_time, problem_id))
                conn.commit()
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=processor,
                measure=f"接单开始处理，处理意见：{processing_comments}",
                department=user_department
            )
            return True
    except Exception as e:
        st.error(f"接单失败: {e}")
        return False

def reject_work_order(problem_id: int, operator: str, reject_reason: str) -> bool:
    """驳回工单 - 按照新业务规则：从已派发状态调整为待处理状态，当前处理部门调整为调度中心"""
    try:
        # 更新工单状态为待处理
        success = db.update_problem_status(problem_id, "待处理", operator, f"工单被驳回，驳回原因：{reject_reason}")
        
        if success:
            # 更新当前处理部门为调度中心，清空处理人
            current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE problems 
                    SET processing_unit = '调度中心', 
                        processing_person = NULL,
                        processing_status = '待处理',
                        is_processing = 0,
                        updated_at = ?
                    WHERE id = ?
                ''', (current_time, problem_id))
                conn.commit()
            
            # 清除多部门关联（如果有），并重新设置调度中心关联
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM problem_departments WHERE problem_id = ?', (problem_id,))
                cursor.execute('''
                    INSERT INTO problem_departments (problem_id, department, is_primary, assigned_at, assigned_by)
                    VALUES (?, ?, 1, ?, ?)
                ''', (problem_id, "调度中心", current_time, operator))
                conn.commit()
            
            # 获取驳回人的真实部门信息
            user_department = '未知部门'
            try:
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT department FROM users WHERE real_name = ?', (operator,))
                    user_result = cursor.fetchone()
                    if user_result and user_result['department']:
                        user_department = user_result['department']
            except Exception as e:
                print(f"获取用户部门信息失败: {e}")
                # 回退到session信息
                user_department = st.session_state.user_info.get('department', '未知部门')
            
            # 添加处理记录 - 增加完整的流转信息
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单被驳回，驳回原因：{reject_reason}，流转至调度中心",
                department=user_department,  # 驳回操作执行人的真实部门
                assigned_to="待分配"  # 流转至调度中心后待分配
            )
            return True
    except Exception as e:
        st.error(f"驳回工单失败: {e}")
        return False

def reassign_work_order(problem_id: int, new_departments: List[str], new_persons: List[str], operator: str, reassign_comments: str = "") -> bool:
    """转派工单"""
    try:
        # 更新工单状态为已派发
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['ASSIGNED'], operator, f"工单转派，转派意见：{reassign_comments}")
        
        if success:
            # 更新工单处理人
            if new_departments and new_persons:
                primary_department = new_departments[0]
                primary_person = new_persons[0]
                db.update_problem_processor(problem_id, primary_person, primary_department)
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单转派，新处理部门：{', '.join(new_departments)}，新处理人：{', '.join(new_persons)}，转派意见：{reassign_comments}",
                department=new_departments[0] if new_departments else None,
                assigned_to=new_persons[0] if new_persons else None
            )
            return True
        return False
    except Exception as e:
        st.error(f"转派工单失败: {e}")
        return False

def reply_work_order(problem_id: int, processor: str, reply_content: str) -> bool:
    """回复处理结果"""
    try:
        # 更新工单状态为已处理回复
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['REPLIED'], processor, f"处理完毕回复，处理结果：{reply_content}")
        
        if success:
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=processor,
                measure=f"处理完毕回复，处理结果：{reply_content}",
                department=st.session_state.user_info.get('department', '')
            )
            return True
        return False
    except Exception as e:
        st.error(f"回复处理结果失败: {e}")
        return False

def close_work_order(problem_id: int, operator: str, close_comments: str = "") -> bool:
    """办结工单"""
    try:
        # 更新工单状态为已办结
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['RESOLVED'], operator, f"工单已办结，办结意见：{close_comments}")
        
        if success:
            # 确保设置is_resolved标志为1，processing_status为已办结
            current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE problems 
                    SET is_resolved = 1, 
                        processing_status = '已办结',
                        is_processing = 0,
                        updated_at = ?
                    WHERE id = ?
                ''', (current_time, problem_id))
                conn.commit()
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单已办结，办结意见：{close_comments}",
                department=st.session_state.user_info.get('department', '')
            )
            return True
        return False
    except Exception as e:
        st.error(f"办结工单失败: {e}")
        return False

def reopen_work_order(problem_id: int, operator: str) -> bool:
    """重新开启工单"""
    try:
        # 更新工单状态为处理中
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['PROCESSING'], operator, "工单重新开启")
        
        if success:
            # 重要：更新工单的其他状态字段，确保重新开启后可以正常操作
            current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            with db._get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查字段是否存在，如果不存在则跳过
                cursor.execute("PRAGMA table_info(problems)")
                columns = [column[1] for column in cursor.fetchall()]
                
                update_fields = []
                update_values = []
                
                if 'is_resolved' in columns:
                    update_fields.append('is_resolved = ?')
                    update_values.append(0)
                
                if 'is_processing' in columns:
                    update_fields.append('is_processing = ?')
                    update_values.append(1)
                
                if 'processing_status' in columns:
                    update_fields.append('processing_status = ?')
                    update_values.append('处理中')
                
                # 添加更新时间
                update_fields.append('updated_at = ?')
                update_values.append(current_time)
                
                # 添加工单ID
                update_values.append(problem_id)
                
                if update_fields:
                    query = f'''
                        UPDATE problems 
                        SET {', '.join(update_fields)}
                        WHERE id = ?
                    '''
                    cursor.execute(query, update_values)
                    conn.commit()
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure="工单重新开启",
                department=st.session_state.user_info.get('department', '')
            )
            return True
        return False
    except Exception as e:
        st.error(f"重新开启工单失败: {e}")
        return False

def reject_reply(problem_id: int, operator: str, reject_reason: str, reject_type: str = "all", target_departments: List[str] = None) -> bool:
    """
    驳回处理回复 - 支持全部驳回和指定驳回
    
    Args:
        problem_id: 工单ID
        operator: 操作人
        reject_reason: 驳回原因
        reject_type: 驳回类型 ("all"=全部驳回, "specific"=指定部门驳回)
        target_departments: 指定驳回的部门列表（仅在reject_type="specific"时使用）
    """
    try:
        # 获取工单信息
        problem = db.get_problem_by_id(problem_id)
        if not problem:
            return False
        
        # 获取工单的所有受理部门
        problem_departments = db.get_problem_departments(problem_id)
        is_collaborative = len(problem_departments) > 1
        
        # 更新工单状态为处理中
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['PROCESSING'], operator, f"驳回处理回复，驳回原因：{reject_reason}")
        
        if success:
            current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            with db._get_connection() as conn:
                cursor = conn.cursor()
                
                if is_collaborative:
                    # 协同工单驳回逻辑
                    if reject_type == "all":
                        # 全部驳回：所有协同部门重新处理
                        # 找到主要处理部门（通常是第一个部门）
                        main_department = None
                        for dept in problem_departments:
                            if dept.get('is_primary', 0) == 1:
                                main_department = dept.get('department')
                                break
                        
                        if not main_department:
                            # 如果没有主要部门，使用第一个部门
                            main_department = problem_departments[0].get('department')
                        
                        # 更新工单的processing_unit为主部门
                        cursor.execute('''
                            UPDATE problems 
                            SET processing_unit = ?, processing_status = ?, updated_at = ?
                            WHERE id = ?
                        ''', (main_department, WORK_ORDER_STATUS['PROCESSING'], current_time, problem_id))
                        
                        # 保持多部门关联，不清除problem_departments
                        # 添加驳回记录
                        db.add_processing_record(
                            problem_id=problem_id,
                            processor=operator,
                            measure=f"驳回协同处理回复（全部驳回），驳回原因：{reject_reason}，所有协同部门需重新处理",
                            department=st.session_state.user_info.get('department', ''),
                            assigned_to=main_department
                        )
                        
                    else:  # reject_type == "specific"
                        # 指定驳回：只驳回特定部门
                        if not target_departments:
                            st.error("指定驳回时必须选择目标部门")
                            return False
                        
                        # 更新工单的processing_unit为第一个指定部门
                        first_target = target_departments[0]
                        cursor.execute('''
                            UPDATE problems 
                            SET processing_unit = ?, processing_status = ?, updated_at = ?
                            WHERE id = ?
                        ''', (first_target, WORK_ORDER_STATUS['PROCESSING'], current_time, problem_id))
                        
                        # 保持多部门关联，但标记被驳回的部门需要重新处理
                        # 添加驳回记录
                        target_dept_str = "、".join(target_departments)
                        db.add_processing_record(
                            problem_id=problem_id,
                            processor=operator,
                            measure=f"驳回协同处理回复（指定驳回），驳回原因：{reject_reason}，指定部门需重新处理：{target_dept_str}",
                            department=st.session_state.user_info.get('department', ''),
                            assigned_to=first_target
                        )
                        
                else:
                    # 非协同工单：使用原有逻辑
                    # 获取处理记录，找到最近的"处理回复"记录，确定原处理部门和处理人
                    processing_records = db.get_processing_records(problem_id)
                    original_department = None
                    original_processor = None
                    
                    # 从最新的处理记录往前找，找到最近的"处理回复"记录
                    for record in reversed(processing_records):
                        measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
                        if "处理回复" in measure and "流转至" in measure:
                            # 这是处理回复记录，获取原处理部门和处理人
                            original_department = record.get('department') if hasattr(record, 'get') else (record['department'] if 'department' in record.keys() else None)
                            original_processor = record.get('processor') if hasattr(record, 'get') else (record['processor'] if 'processor' in record.keys() else None)
                            break
                    
                    # 如果没找到原处理部门，使用默认逻辑
                    if not original_department:
                        # 备用方案：从最近的转派记录中获取目标部门
                        try:
                            for record in reversed(processing_records):
                                measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
                                if "调度中心转派" in measure and "转派部门：" in measure:
                                    # 从转派记录中提取目标部门
                                    import re
                                    match = re.search(r'转派部门：([^，]+)', measure)
                                    if match:
                                        original_department = match.group(1)
                                        break
                        except:
                            pass
                        
                        # 如果还没找到，设为待分配
                        if not original_department:
                            original_department = "待分配"
                    
                    if not original_processor:
                        original_processor = "待分配"
                    
                    # 更新工单的processing_unit，将工单重新分配给原处理部门
                    cursor.execute('''
                        UPDATE problems 
                        SET processing_unit = ?, processing_status = ?, updated_at = ?
                        WHERE id = ?
                    ''', (original_department, WORK_ORDER_STATUS['PROCESSING'], current_time, problem_id))
                    
                    # 更新工单部门关联 - 清除原有关联，重新分配给原处理部门
                    cursor.execute('DELETE FROM problem_departments WHERE problem_id = ?', (problem_id,))
                    cursor.execute('''
                        INSERT INTO problem_departments (problem_id, department, is_primary, assigned_at, assigned_by)
                        VALUES (?, ?, 1, ?, ?)
                    ''', (problem_id, original_department, current_time, operator))
                    
                    # 添加处理记录 - 包含完整的流转信息
                    db.add_processing_record(
                        problem_id=problem_id,
                        processor=operator,
                        measure=f"驳回处理回复，驳回原因：{reject_reason}，流转至{original_department}",
                        department=st.session_state.user_info.get('department', ''),
                        assigned_to=original_processor  # 流转至原处理人
                    )
                
                conn.commit()
            return True
        return False
    except Exception as e:
        st.error(f"驳回处理回复失败: {e}")
        return False

def collaborate_work_order(problem_id: int, main_department: str, collaborate_departments: List[str], operator: str, collaborate_comments: str = "", collaborate_persons: List[str] = []) -> bool:
    """协同工单处理"""
    try:
        # 更新工单状态为处理中
        success = db.update_problem_status(problem_id, "处理中", operator, f"协同处理，协同意见：{collaborate_comments}")
        
        if success:
            # 设置多部门：主要处理部门为当前部门，添加协同部门
            all_departments = [main_department] + collaborate_departments
            db.assign_to_multiple_departments(problem_id, all_departments, operator)
            
            # 更新工单状态字段
            with db._get_connection() as conn:
                cursor = conn.cursor()
                current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                    UPDATE problems 
                    SET is_processing = 1, processing_status = '处理中', updated_at = ?
                    WHERE id = ?
                ''', (current_time, problem_id))
                conn.commit()
            
            # 构建协同信息字符串
            collaborate_info_parts = [
                f"主要部门：{main_department}",
                f"协同部门：{', '.join(collaborate_departments)}"
            ]
            
            # 如果有协同处理人，添加到信息中
            if collaborate_persons:
                collaborate_info_parts.append(f"协同处理人：{', '.join(collaborate_persons)}")
            
            collaborate_info_parts.append(f"协同意见：{collaborate_comments}")
            collaborate_info = "，".join(collaborate_info_parts)
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"协同处理，{collaborate_info}",
                department=main_department,
                assigned_to=operator
            )
            
            return True
    except Exception as e:
        print(f"协同工单失败: {e}")
        return False

def process_reply_work_order(problem_id: int, processor: str, reply_content: str) -> bool:
    """处理回复工单 - 重新设计协同工单流转逻辑"""
    try:
        # 获取工单信息
        problem = db.get_problem_by_id(problem_id)
        if not problem:
            return False
        
        # 获取工单的所有受理部门
        problem_departments = db.get_problem_departments(problem_id)
        is_collaborative = len(problem_departments) > 1
        
        # 更新工单状态为已处理回复
        success = db.update_problem_status(problem_id, "已处理回复", processor, f"处理回复：{reply_content}")
        
        if success:
            # 协同工单流转逻辑
            if is_collaborative:
                # 检查是否所有协同部门都已处理回复
                all_departments_processed = check_all_collaborative_departments_processed(problem_id)
                
                if all_departments_processed:
                    # 所有协同部门都已处理，流转至调度中心
                    target_department = "调度中心"
                    target_person = "待分配"
                    # 清除多部门关联，流转至调度中心
                    clear_multiple_departments = True
                else:
                    # 还有部门未处理，保持当前状态，不流转
                    target_department = problem.get('processing_unit', '')
                    target_person = problem.get('processing_person', '')
                    # 保持多部门关联
                    clear_multiple_departments = False
            else:
                # 非协同工单：流转回调度中心
                target_department = "调度中心"
                target_person = "待分配"
                clear_multiple_departments = True
            
            # 更新当前处理部门
            current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            with db._get_connection() as conn:
                cursor = conn.cursor()
                
                if clear_multiple_departments:
                    # 流转至调度中心时，更新处理部门
                    cursor.execute('''
                        UPDATE problems 
                        SET processing_unit = ?, processing_status = '已处理回复', updated_at = ?
                        WHERE id = ?
                    ''', (target_department, current_time, problem_id))
                    
                    # 清除多部门关联，但保留调度中心关联
                    cursor.execute('DELETE FROM problem_departments WHERE problem_id = ?', (problem_id,))
                    cursor.execute('''
                        INSERT INTO problem_departments (problem_id, department, is_primary, assigned_at, assigned_by)
                        VALUES (?, ?, 1, ?, ?)
                    ''', (problem_id, target_department, current_time, processor))
                    
                    # 重要：在流转至调度中心时，添加一条特殊的处理记录，记录所有协同部门的处理情况
                    if is_collaborative:
                        # 获取所有协同部门的处理回复记录
                        cursor.execute('''
                            SELECT pd.department, pr.measure, pr.processor, pr.created_at
                            FROM problem_departments pd
                            LEFT JOIN processing_records pr ON pd.problem_id = pr.problem_id 
                                AND pd.department = pr.department 
                                AND pr.measure LIKE '%处理回复%'
                            WHERE pd.problem_id = ? AND pd.department != '调度中心'
                            ORDER BY pd.is_primary DESC, pd.assigned_at ASC
                        ''', (problem_id,))
                        
                        collaborative_replies = cursor.fetchall()
                        if collaborative_replies:
                            # 合并所有回复记录到一个表格中，共用表头
                            all_reply_data = []
                            for record in collaborative_replies:
                                # 安全地访问字段
                                department = record[0]
                                processor = record[2]
                                measure = record[1]
                                created_at = record[3]
                                
                                # 提取处理回复的实际内容
                                import re
                                # 从"处理回复，流转至调度中心：实际内容"或"处理回复（协同处理中）：实际内容"中提取实际内容
                                content_match = re.search(r'：(.+)$', measure)
                                reply_content = content_match.group(1) if content_match else measure
                                
                                # 判断是否为协同处理中的回复
                                is_collaborative = "协同处理中" in measure
                                status_text = "（协同处理中）" if is_collaborative else "（已完成）"
                                
                                # 添加到数据列表
                                all_reply_data.append({
                                    '处理部门': department,
                                    '处理人': processor,
                                    '处理状态': status_text,
                                    '处理结果': reply_content,
                                    '处理时间': created_at
                                })
                            
                            # 创建合并后的DataFrame并显示
                            import pandas as pd
                            df = pd.DataFrame(all_reply_data)
                            st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    # 保持当前状态，只更新时间
                    cursor.execute('''
                        UPDATE problems 
                        SET updated_at = ?
                        WHERE id = ?
                    ''', (current_time, problem_id))
                
                conn.commit()
            
            # 添加处理记录
            user_department = st.session_state.user_info.get('department', '')
            if clear_multiple_departments:
                measure_text = f"处理回复，流转至{target_department}：{reply_content}"
            else:
                measure_text = f"处理回复（协同处理中）：{reply_content}"
            
            db.add_processing_record(
                problem_id=problem_id,
                processor=processor,
                measure=measure_text,
                department=user_department,
                assigned_to=target_person
            )
            
            return True
    except Exception as e:
        print(f"处理回复失败: {e}")
        return False

def check_all_collaborative_departments_processed(problem_id):
    """检查协同工单的所有部门是否都已处理回复"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取所有协同部门（排除调度中心）
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

def render_work_order_detail(problem: Dict):
    """渲染工单详情"""
    # 格式化工单号
    work_order_id = f"WT{str(problem['id']).zfill(5)}"
    
    # 使用Streamlit原生组件替代HTML
    st.markdown(f"### {problem['title']}")
    
    # 工单号和状态行
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**工单号:** {work_order_id}")
    with col2:
        status = problem.get('status', '待处理')
        if status == '待处理':
            st.info("待处理")
        elif status == '已派发':
            st.warning("已派发")
        elif status == '处理中':
            st.success("处理中")
        elif status == '已处理回复':
            st.info("已处理回复")
        elif status == '已办结':
            st.success("已办结")
        else:
            st.info(status)
    
    # 检查是否为协同工单，如果是则显示协同处理进度
    is_collaborative = is_collaboration_work_order(problem['id'])
    if is_collaborative:
        st.markdown("#### 🔄 协同处理进度")
        render_collaborative_progress(problem['id'])
        # 删除分隔符，让界面更紧凑
        # st.divider()
    
    # 发布工单信息区域
    st.markdown("#### 📋 发布工单")
    
    # 使用容器和列布局
    with st.container():
        # 第一行：发布人和发布时间
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**发布人：** {problem['author']}")
        with col2:
            st.markdown(f"**发布时间：** {problem.get('created_at', '未设置')}")
        
        # 第二行：初始状态和接收部门
        col3, col4 = st.columns(2)
        with col3:
            st.markdown(f"**初始状态：** 待处理")
        with col4:
            st.markdown(f"**接收部门：** {problem.get('response_department', '调度中心')}")
        
        # 第三行：下步处理
        response_department = problem.get('response_department', '调度中心')
        if response_department == '调度中心':
            st.markdown(f"**下步处理：** 等待调度中心派单")
        else:
            st.markdown(f"**下步处理：** 直派部门{response_department}")
        
        # 工单内容
        st.markdown("**工单内容：**")
        st.info(problem.get('description', '无描述'))
    
    # 删除分隔符，让界面更紧凑
    # st.divider()
    
    # 工单详细信息
    st.markdown("#### 工单详细信息")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**提交人:** {problem['author']}")
        st.markdown(f"**问题分类:** {problem['category']}")
        st.markdown(f"**优先级:** {problem.get('priority', '普通')}")
    
    with col2:
        st.markdown(f"**提交部门:** {problem.get('department', '未指定')}")
        st.markdown(f"**提交时间:** {problem.get('created_at', '未设置')}")
        st.markdown(f"**当前处理部门:** {problem.get('processing_unit', '-')}")
    
    # 问题描述
    st.markdown("**问题描述：**")
    st.text_area("问题描述", value=problem.get('description', ''), height=100, disabled=True, label_visibility="collapsed")

def render_collaborative_progress(problem_id):
    """渲染协同处理进度"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取所有协同部门
            cursor.execute('''
                SELECT pd.department, pd.is_primary,
                       CASE WHEN pr.id IS NOT NULL THEN 1 ELSE 0 END as has_reply
                FROM problem_departments pd
                LEFT JOIN processing_records pr ON pd.problem_id = pr.problem_id 
                    AND pd.department = pr.department 
                    AND pr.measure LIKE '%处理回复%'
                WHERE pd.problem_id = ? AND pd.department != '调度中心'
                ORDER BY pd.is_primary DESC, pd.assigned_at ASC
            ''', (problem_id,))
            
            departments = cursor.fetchall()
            
            if len(departments) <= 1:
                return
            
            # 创建进度显示
            st.info("📋 协同处理进度（所有部门处理完成后，工单将流转至调度中心）")
            
            # 显示每个部门的处理状态
            for dept, is_primary, has_reply in departments:
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col1:
                    if is_primary:
                        st.markdown("🏢 **主要部门**")
                    else:
                        st.markdown("🤝 **协同部门**")
                
                with col2:
                    if has_reply:
                        st.success(f"✅ {dept} - 已处理回复")
                    else:
                        st.warning(f"⏳ {dept} - 待处理")
                
                with col3:
                    if has_reply:
                        # 显示处理回复内容
                        cursor.execute('''
                            SELECT measure, created_at FROM processing_records 
                            WHERE problem_id = ? AND department = ? 
                            AND measure LIKE '%处理回复%'
                            ORDER BY created_at DESC LIMIT 1
                        ''', (problem_id, dept))
                        
                        reply_record = cursor.fetchone()
                        if reply_record:
                            measure, created_at = reply_record
                            # 提取回复内容
                            if "：" in measure:
                                reply_content = measure.split("：")[-1]
                            else:
                                reply_content = measure
                            
                            with st.expander(f"查看{dept}回复"):
                                st.markdown(f"**回复内容：** {reply_content}")
                                st.markdown(f"**回复时间：** {created_at}")
            
            # 显示总体进度
            processed_count = sum(1 for _, _, has_reply in departments if has_reply)
            total_count = len(departments)
            
            if processed_count == total_count:
                st.success(f"🎉 所有协同部门（{total_count}个）已完成处理，工单已流转至调度中心")
            else:
                st.info(f"📊 处理进度：{processed_count}/{total_count} 个部门已完成")
                
    except Exception as e:
        st.error(f"获取协同处理进度失败: {e}")

def render_work_order_operation(problem: Dict, user_info: Dict):
    """渲染工单操作区域"""
    st.markdown("### 工单调度操作")
    
    status = problem.get('status', '待处理')
    user_role = user_info['role']
    user_name = user_info['real_name']
    user_department = user_info.get('department', '')
    
    # 重新计算显示状态，确保与统计逻辑一致
    display_status = status
    processing_unit = problem.get('processing_unit', '')
    is_processing = problem.get('is_processing', False)
    is_resolved = problem.get('is_resolved', False)
    processing_records_count = problem.get('processing_records_count', 0)
    
    # 检查是否为协同工单
    is_collaborative = is_collaboration_work_order(problem['id'])
    
    # 使用与数据库管理器相同的状态判断逻辑
    if is_resolved:
        display_status = "已办结"
    elif status == '已处理回复':
        if is_collaborative:
            # 协同工单：检查是否所有部门都已处理
            all_departments_processed = check_all_collaborative_departments_processed(problem['id'])
            if all_departments_processed:
                display_status = "已处理回复（协同完成）"
            else:
                display_status = "已处理回复（协同处理中）"
        else:
            display_status = "已处理回复"
    else:
        # 优先检测驳回工单：如果工单被驳回到调度中心，应显示为待处理状态
        is_rejected_to_dispatch = False
        if status == '待处理' and processing_unit == '调度中心' and processing_records_count > 0:
            # 检查是否为驳回工单
            is_rejected_to_dispatch = is_rejected_work_order(problem['id'])
        
        if is_rejected_to_dispatch:
            display_status = "待处理"  # 驳回工单显示为待处理
        elif is_processing or (processing_records_count > 0 and status != '待处理'):
            if is_collaborative:
                display_status = "处理中（协同处理）"
            else:
                display_status = "处理中"
        elif status == '已派发' or (processing_unit and processing_unit.strip() and status != '待处理'):
            if is_collaborative:
                display_status = "已派发（协同派单）"
            else:
                display_status = "已派发"
        else:
            display_status = "待处理"
    
    # 显示当前状态
    if is_collaborative:
        st.info(f"🔄 **当前状态：** {display_status}")
        st.info("📋 **工单类型：** 协同工单（需要所有协同部门处理完成后才能流转至调度中心）")
    else:
        st.info(f"📋 **当前状态：** {display_status}")
    
    # 检查用户是否有权限操作此工单 - 使用新规则
    can_operate = False
    
    if user_role == 'admin':
        if user_department == '调度中心':
            # 归属调度中心的admin：可以操作以下工单：
            # 1. 待处理状态的工单
            # 2. 当前受理部门为调度中心的工单
            # 3. 已处理回复状态且所有协同部门都已处理的协同工单
            can_operate = (
                display_status == '待处理' or 
                processing_unit == '调度中心' or
                (display_status == '已处理回复（协同完成）' and is_collaborative)
            )
        else:
            # 其他部门的admin：只能操作当前受理部门为自己部门的工单
            # 但是：如果工单状态为"已处理回复"且当前处理部门不是自己部门，则没有权限
            if display_status == '已处理回复' and processing_unit != user_department:
                can_operate = False
            else:
                can_operate = (processing_unit == user_department)
    else:
        # processor和manager角色
        if user_department == '调度中心':
            # 归属调度中心的processor、manager：可以操作以下工单：
            # 1. 待处理状态的工单
            # 2. 当前受理部门为调度中心的工单
            # 3. 已处理回复状态且所有协同部门都已处理的协同工单
            can_operate = (
                display_status == '待处理' or 
                processing_unit == '调度中心' or
                (display_status == '已处理回复（协同完成）' and is_collaborative)
            )
        else:
            # 其他部门的processor、manager：检查是否有权限操作
            # 1. 当前受理部门为自己部门
            # 2. 或者工单被分配给自己部门（通过problem_departments表）
            # 3. 或者自己部门是协作部门
            # 4. 但是：如果工单状态为"已处理回复"且当前处理部门不是自己部门，则没有权限
            if display_status == '已处理回复' and processing_unit != user_department:
                can_operate = False
            else:
                can_operate = (
                    processing_unit == user_department or
                    db.is_department_assigned_to_problem(problem['id'], user_department) or
                    db.is_department_collaborating_on_problem(problem['id'], user_department)
                )
    
    # 检查是否为调度中心用户
    is_dispatch_center = user_department == '调度中心'
    
    # 如果没有权限操作，直接返回
    if not can_operate:
        st.info("您没有权限操作此工单")
        return
    
    # 待处理状态 - 调度中心可以转派，admin可以派发
    if display_status == '待处理':
        if is_dispatch_center:
            render_dispatch_center_operation(problem, user_info)
        elif user_role == 'admin':
            render_dispatch_operation(problem, user_info)
        else:
            st.info("您没有权限操作此工单")
    
    # 已派发状态 - 部门处理人可以接单、驳回、转派
    elif '已派发' in display_status and can_operate:
        render_assigned_operation(problem, user_info)
    
    # 处理中状态 - 部门处理人可以回复处理、转派
    elif '处理中' in display_status and can_operate:
        render_processing_operation(problem, user_info)
    
    # 已处理回复状态 - 调度中心可以确认或驳回，部门处理人可以继续处理、转派
    elif '已处理回复' in display_status:
        if is_dispatch_center:
            render_dispatch_center_review_operation(problem, user_info)
        elif can_operate:
            render_replied_operation(problem, user_info)
        else:
            st.info("您没有权限操作此工单")
    
    # 已办结状态 - 仅admin可以重新开启
    elif display_status == '已办结' and user_role == 'admin':
        render_resolved_operation(problem, user_info)
    
    else:
        st.info("您没有权限操作此工单或工单状态不允许当前操作")

def render_dispatch_center_operation(problem: Dict, user_info: Dict):
    """渲染调度中心转派操作"""
    
    # 检查是否为驳回工单
    is_rejected = is_rejected_work_order(problem['id'])
    
    if is_rejected:
        st.write("**操作类型:** 驳回工单重新派单")
    else:
        st.write("**操作类型:** 调度中心转派工单")
    
    # 检查是否有驳回记录并显示
    processing_records = db.get_processing_records(problem['id'])
    if processing_records:
        latest_reject = None
        for record in reversed(processing_records):
            # 查找最新的驳回记录
            measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
            if "工单被驳回" in measure or "驳回" in measure:
                latest_reject = record
                break
        
        if latest_reject:
            # 显示驳回信息
            st.subheader("📋 驳回信息")
            
            # 安全地访问字段
            department = latest_reject.get('department', '未知部门') if hasattr(latest_reject, 'get') else (latest_reject['department'] if 'department' in latest_reject.keys() else '未知部门')
            processor = latest_reject.get('processor', '未知处理人') if hasattr(latest_reject, 'get') else (latest_reject['processor'] if 'processor' in latest_reject.keys() else '未知处理人')
            measure = latest_reject.get('measure', '无驳回信息') if hasattr(latest_reject, 'get') else (latest_reject['measure'] if 'measure' in latest_reject.keys() else '无驳回信息')
            created_at = latest_reject.get('created_at', '未知时间') if hasattr(latest_reject, 'get') else (latest_reject['created_at'] if 'created_at' in latest_reject.keys() else '未知时间')
            
            # 提取驳回原因
            import re
            # 从"工单被驳回，驳回原因：具体原因，流转至调度中心"中提取驳回原因
            reason_match = re.search(r'驳回原因：([^，]+)', measure)
            reject_reason = reason_match.group(1) if reason_match else '无具体原因'
            
            # 使用表格形式显示驳回信息
            import pandas as pd
            
            # 创建表格数据
            reject_data = {
                '驳回部门': [department],
                '驳回人': [processor],
                '驳回原因': [reject_reason],
                '驳回时间': [created_at]
            }
            
            # 显示表格
            df = pd.DataFrame(reject_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    # 重新派单界面（对于驳回工单和普通工单都显示相同的派单界面）
    st.subheader("🎯 重新派单" if is_rejected else "📤 工单派单")
    
    # 获取所有部门（排除调度中心）
    departments = [dept for dept in get_all_departments() if dept != '调度中心']
    
    # 使用列布局将转派部门和处理人放在同一行
    col1, col2 = st.columns(2)
    
    with col1:
        # 处理部门选择（可多选）
        selected_departments = st.multiselect(
            "派单部门 (可多选)" if is_rejected else "转派部门 (可多选)",
            departments,
            default=[],
            help="请选择处理部门(可多选)"
        )
    
    with col2:
        # 处理人选择（可多选）
        selected_persons = []
        if selected_departments:
            all_processors = []
            for dept in selected_departments:
                processors = db.get_department_processors(dept)
                all_processors.extend([f"{p['real_name']} ({dept})" for p in processors])
            
            if all_processors:
                selected_persons = st.multiselect(
                    "处理人 (可多选)",
                    all_processors,
                    default=[],
                    help="请选择处理人"
                )
            else:
                st.warning("所选部门暂无处理人")
    
    # 派单意见
    dispatch_comments = st.text_area(
        "派单意见" if is_rejected else "转派意见",
        placeholder="请输入派单意见..." if is_rejected else "请输入转派意见...",
        height=100
    )
    
    # 确认派单按钮
    button_text = "确认重新派单" if is_rejected else "确认转派"
    if st.button(button_text, type="primary"):
        if selected_departments and selected_persons:
            # 提取处理人姓名（去掉部门信息）
            person_names = [p.split(' (')[0] for p in selected_persons]
            
            if dispatch_from_center(problem['id'], selected_departments, person_names, user_info['real_name'], dispatch_comments):
                success_message = "工单重新派单成功！" if is_rejected else "工单转派成功！"
                st.success(success_message)
                # 自动跳转回工单调度首页
                st.switch_page("pages/工单调度.py")
            else:
                st.error("派单失败，请重试")
        else:
            st.error("请选择处理部门和处理人")

def render_dispatch_center_review_operation(problem: Dict, user_info: Dict):
    """渲染调度中心确认操作"""
    st.write("**操作类型:** 调度中心确认处理结果")
    
    # 显示处理部门回复内容 - 修复查询逻辑
    st.subheader("处理部门回复")
    
    # 获取所有处理记录，查找处理回复相关的记录
    processing_records = db.get_processing_records(problem['id'])
    if processing_records:
        # 查找所有处理回复记录（包括协同处理中的回复）
        reply_records = []
        for record in processing_records:
            measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
            if "处理回复" in measure:
                reply_records.append(record)
        
        if reply_records:
            st.success(f"找到 {len(reply_records)} 条处理回复记录")
            
            # 合并所有回复记录到一个表格中，共用表头
            all_reply_data = []
            for record in reply_records:
                # 安全地访问字段
                department = record.get('department', '未知部门') if hasattr(record, 'get') else (record['department'] if 'department' in record.keys() else '未知部门')
                processor = record.get('processor', '未知处理人') if hasattr(record, 'get') else (record['processor'] if 'processor' in record.keys() else '未知处理人')
                measure = record.get('measure', '无处理内容') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '无处理内容')
                created_at = record.get('created_at', '未知时间') if hasattr(record, 'created_at') else (record['created_at'] if 'created_at' in record.keys() else '未知时间')
                
                # 提取处理回复的实际内容
                import re
                # 从"处理回复，流转至调度中心：实际内容"或"处理回复（协同处理中）：实际内容"中提取实际内容
                content_match = re.search(r'：(.+)$', measure)
                reply_content = content_match.group(1) if content_match else measure
                
                # 判断是否为协同处理中的回复
                is_collaborative = "协同处理中" in measure
                status_text = "（协同处理中）" if is_collaborative else "（已完成）"
                
                # 添加到数据列表
                all_reply_data.append({
                    '处理部门': department,
                    '处理人': processor,
                    '处理状态': status_text,
                    '处理结果': reply_content,
                    '处理时间': created_at
                })
            
            # 创建合并后的DataFrame并显示
            import pandas as pd
            df = pd.DataFrame(all_reply_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("未找到处理回复记录")
            
            # 删除调试信息选择项
            # if st.checkbox("显示调试信息", key="debug_reply_records"):
            #     st.write("所有处理记录：")
            #     for record in processing_records:
            #         measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
            #         st.write(f"- {measure}")
    else:
        st.warning("未找到任何处理记录")
    
    # 操作选择
    operation_choice = st.radio(
        "请选择操作",
        ["确认办结", "驳回继续处理"],
        help="确认办结将关闭工单，驳回继续处理将让处理部门重新处理"
    )
    
    if operation_choice == "确认办结":
        # 办结意见
        close_comments = st.text_area(
            "办结意见",
            placeholder="请输入办结意见...",
            height=100
        )
        
        # 确认办结按钮
        if st.button("确认办结", type="primary"):
            if close_work_order(problem['id'], user_info['real_name'], close_comments):
                st.success("工单已办结！")
                # 自动跳转回工单调度首页
                st.switch_page("pages/工单调度.py")
            else:
                st.error("办结失败，请重试")
    
    else:  # 驳回继续处理
        # 驳回类型选择
        reject_type = st.radio(
            "驳回类型",
            ["全部驳回", "指定部门驳回"],
            help="全部驳回：所有协同部门重新处理；指定驳回：只驳回特定部门"
        )
        
        # 驳回原因
        reject_reason = st.text_area(
            "驳回原因",
            placeholder="请输入驳回原因...",
            height=100
        )
        
        # 如果是协同工单且选择指定驳回，显示部门选择
        target_departments = []
        if reject_type == "指定部门驳回":
            # 检查是否为协同工单
            problem_departments = db.get_problem_departments(problem['id'])
            is_collaborative = len(problem_departments) > 1
            
            if is_collaborative:
                # 获取所有协同部门（排除调度中心）
                collaborative_depts = []
                for dept in problem_departments:
                    if dept.get('department') != '调度中心':
                        collaborative_depts.append(dept.get('department'))
                
                if collaborative_depts:
                    target_departments = st.multiselect(
                        "选择需要重新处理的部门",
                        collaborative_depts,
                        default=collaborative_depts,  # 默认全选
                        help="选择需要重新处理的部门，未选择的部门将保持当前状态"
                    )
                else:
                    st.warning("未找到可驳回的协同部门")
            else:
                st.info("非协同工单，将使用全部驳回模式")
                reject_type = "全部驳回"
        
        # 确认驳回按钮
        if st.button("确认驳回", type="primary"):
            if reject_reason.strip():
                # 验证指定驳回时必须选择部门
                if reject_type == "指定部门驳回" and not target_departments:
                    st.error("请选择需要重新处理的部门")
                    return
                
                # 转换驳回类型
                reject_type_code = "specific" if reject_type == "指定部门驳回" else "all"
                
                if reject_reply(problem['id'], user_info['real_name'], reject_reason, reject_type_code, target_departments):
                    # 显示驳回后的状态信息
                    if reject_type == "全部驳回":
                        st.success("工单已全部驳回！所有协同部门将重新处理。")
                    else:
                        target_dept_str = "、".join(target_departments)
                        st.success(f"工单已指定驳回！部门 {target_dept_str} 将重新处理。")
                    
                    # 显示流转信息
                    st.info("工单将流转至主要处理部门，请等待相关部门重新处理。")
                    
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    st.error("驳回失败，请重试")
            else:
                st.error("请填写驳回原因")

def render_dispatch_operation(problem: Dict, user_info: Dict):
    """渲染派发工单操作"""
    st.write("**操作类型:** 派发工单")
    
    # 获取所有部门
    departments = get_all_departments()
    
    # 使用列布局将处理部门和处理人放在同一行
    col1, col2 = st.columns(2)
    
    with col1:
        # 处理部门选择（可多选）
        selected_departments = st.multiselect(
            "处理部门 (可多选)",
            departments,
            default=[],
            help="请选择部门(可多选)"
        )
    
    with col2:
        # 处理人选择（可多选）
        selected_persons = []
        if selected_departments:
            all_processors = []
            for dept in selected_departments:
                processors = db.get_department_processors(dept)
                all_processors.extend([f"{p['real_name']} ({dept})" for p in processors])
            
            if all_processors:
                selected_persons = st.multiselect(
                    "处理人 (可多选)",
                    all_processors,
                    default=[],
                    help="请选择处理人"
                )
            else:
                st.warning("所选部门暂无处理人")
    
    # 派发意见
    dispatch_comments = st.text_area(
        "派发意见",
        placeholder="请输入派发意见...",
        height=100
    )
    
    # 确认派发按钮
    if st.button("确认派发", type="primary"):
        if selected_departments and selected_persons:
            # 提取处理人姓名（去掉部门信息）
            person_names = [p.split(' (')[0] for p in selected_persons]
            
            if assign_work_order(problem['id'], selected_departments, person_names, user_info['real_name'], dispatch_comments):
                st.success("工单派发成功！")
                # 自动跳转回工单调度首页
                st.switch_page("pages/工单调度.py")
            else:
                st.error("派发失败，请重试")
        else:
            st.error("请选择处理部门和处理人")

def render_assigned_operation(problem: Dict, user_info: Dict):
    """渲染已派发工单操作"""
    operation_type = st.selectbox(
        "操作类型",
        ["接单处理", "处理回复", "驳回工单", "协同工单"],
        help="请选择要执行的操作"
    )
    
    if operation_type == "接单处理":
        st.write("**操作类型:** 接单处理")
        
        # 处理意见
        processing_comments = st.text_area(
            "处理意见",
            placeholder="请输入处理意见...",
            height=100
        )
        
        # 确认接单按钮
        if st.button("确认接单", type="primary"):
            if accept_work_order(problem['id'], user_info['real_name'], processing_comments):
                st.success("接单成功！工单状态已调整为处理中")
                # 自动跳转回工单调度首页
                st.switch_page("pages/工单调度.py")
            else:
                st.error("接单失败，请重试")
    
    elif operation_type == "处理回复":
        st.write("**操作类型:** 处理回复")
        
        # 处理意见
        reply_content = st.text_area(
            "处理意见",
            placeholder="请输入处理结果和解决方案...",
            height=150
        )
        
        # 确认回复按钮
        if st.button("确认回复", type="primary"):
            # 防重复提交：检查是否已经在处理中
            if 'reply_processing' not in st.session_state:
                st.session_state.reply_processing = False
            
            if st.session_state.reply_processing:
                st.warning("正在处理中，请勿重复点击...")
                return
            
            if reply_content.strip():
                # 设置处理中状态
                st.session_state.reply_processing = True
                
                if process_reply_work_order(problem['id'], user_info['real_name'], reply_content):
                    st.success("处理回复成功！工单已流转")
                    # 重置处理状态
                    st.session_state.reply_processing = False
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    # 失败时重置处理状态
                    st.session_state.reply_processing = False
                    st.error("处理回复失败，请重试")
            else:
                st.error("请填写处理结果")
    
    elif operation_type == "驳回工单":
        st.write("**操作类型:** 驳回工单")
        
        # 驳回原因
        reject_reason = st.text_area(
            "驳回原因",
            placeholder="请输入驳回原因...",
            height=100,
            help="驳回原因必填"
        )
        
        # 确认驳回按钮
        if st.button("确认驳回", type="primary"):
            if reject_reason.strip():
                if reject_work_order(problem['id'], user_info['real_name'], reject_reason):
                    st.success("工单已驳回！")
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    st.error("驳回失败，请重试")
            else:
                st.error("请填写驳回原因")
    
    else:  # 协同工单
        st.write("**操作类型:** 协同工单")
        
        # 获取所有部门（排除当前部门）
        all_departments = get_all_departments()
        current_department = user_info.get('department', '')
        available_departments = [dept for dept in all_departments if dept != current_department and dept != '调度中心']
        
        # 使用列布局将协同部门和处理人放在同一行，参照图1样式
        col1, col2 = st.columns(2)
        
        with col1:
            # 协同部门选择
            collaborate_departments = st.multiselect(
                "协同部门 (可多选)",
                available_departments,
                default=[],
                help="请选择需要协同处理的部门"
            )
        
        with col2:
            # 协同处理人选择（基于选择的协同部门）
            selected_collaborate_persons = []
            if collaborate_departments:
                all_collaborate_processors = []
                for dept in collaborate_departments:
                    processors = db.get_department_processors(dept)
                    all_collaborate_processors.extend([f"{p['real_name']} ({dept})" for p in processors])
                
                if all_collaborate_processors:
                    selected_collaborate_persons = st.multiselect(
                        "协同处理人 (可多选)",
                        all_collaborate_processors,
                        default=[],
                        help="请选择协同处理人员"
                    )
                else:
                    st.warning("所选协同部门暂无处理人")
        
        # 协同意见
        collaborate_comments = st.text_area(
            "协同意见",
            placeholder="请输入协同处理的原因和要求...",
            height=100
        )
        
        # 协同派单按钮
        if st.button("协同派单", type="primary"):
            # 防重复提交：检查是否已经在处理中
            if 'collaborate_processing' not in st.session_state:
                st.session_state.collaborate_processing = False
            
            if st.session_state.collaborate_processing:
                st.warning("正在处理中，请勿重复点击...")
                return
            
            if collaborate_departments and collaborate_comments.strip():
                # 设置处理中状态
                st.session_state.collaborate_processing = True
                
                # 提取协同处理人姓名（去掉部门信息）
                collaborate_person_names = [p.split(' (')[0] for p in selected_collaborate_persons] if selected_collaborate_persons else []
                
                if collaborate_work_order(problem['id'], current_department, collaborate_departments, user_info['real_name'], collaborate_comments, collaborate_person_names):
                    st.success("协同派单成功！工单状态已调整为处理中，已设置多部门处理")
                    # 重置处理状态
                    st.session_state.collaborate_processing = False
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    # 失败时重置处理状态
                    st.session_state.collaborate_processing = False
                    st.error("协同派单失败，请重试")
            else:
                st.error("请选择协同部门并填写协同意见")

def render_processing_operation(problem: Dict, user_info: Dict):
    """渲染处理中工单操作"""
    operation_type = st.selectbox(
        "操作类型",
        ["接单处理", "处理回复", "驳回工单", "协同工单"],
        help="请选择要执行的操作"
    )
    
    if operation_type == "接单处理":
        st.write("**操作类型:** 接单处理")
        
        # 处理意见
        processing_comments = st.text_area(
            "处理意见",
            placeholder="请输入处理意见...",
            height=100
        )
        
        # 确认接单按钮
        if st.button("确认接单", type="primary"):
            if accept_work_order(problem['id'], user_info['real_name'], processing_comments):
                st.success("接单成功！工单状态已调整为处理中")
                # 自动跳转回工单调度首页
                st.switch_page("pages/工单调度.py")
            else:
                st.error("接单失败，请重试")
    
    elif operation_type == "处理回复":
        st.write("**操作类型:** 处理回复")
        
        # 处理结果
        reply_content = st.text_area(
            "处理结果",
            placeholder="请输入处理结果...",
            height=150,
            help="请详细描述处理结果和解决方案"
        )
        
        # 确认回复按钮
        if st.button("确认回复", type="primary"):
            # 防重复提交：检查是否已经在处理中
            if 'reply_processing' not in st.session_state:
                st.session_state.reply_processing = False
            
            if st.session_state.reply_processing:
                st.warning("正在处理中，请勿重复点击...")
                return
            
            if reply_content.strip():
                # 设置处理中状态
                st.session_state.reply_processing = True
                
                if process_reply_work_order(problem['id'], user_info['real_name'], reply_content):
                    st.success("处理回复成功！工单已流转")
                    # 重置处理状态
                    st.session_state.reply_processing = False
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    # 失败时重置处理状态
                    st.session_state.reply_processing = False
                    st.error("处理回复失败，请重试")
            else:
                st.error("请填写处理结果")
    
    elif operation_type == "驳回工单":
        st.write("**操作类型:** 驳回工单")
        
        # 驳回原因
        reject_reason = st.text_area(
            "驳回原因",
            placeholder="请输入驳回原因...",
            height=100,
            help="驳回原因必填"
        )
        
        # 确认驳回按钮
        if st.button("确认驳回", type="primary"):
            if reject_reason.strip():
                if reject_work_order(problem['id'], user_info['real_name'], reject_reason):
                    st.success("工单已驳回！")
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    st.error("驳回失败，请重试")
            else:
                st.error("请填写驳回原因")
    
    else:  # 协同工单
        st.write("**操作类型:** 协同工单")
        
        # 获取所有部门（排除当前部门）
        all_departments = get_all_departments()
        current_department = user_info.get('department', '')
        available_departments = [dept for dept in all_departments if dept != current_department and dept != '调度中心']
        
        # 使用列布局将协同部门和处理人放在同一行，参照图1样式
        col1, col2 = st.columns(2)
        
        with col1:
            # 协同部门选择
            collaborate_departments = st.multiselect(
                "协同部门 (可多选)",
                available_departments,
                default=[],
                help="请选择需要协同处理的部门"
            )
        
        with col2:
            # 协同处理人选择（基于选择的协同部门）
            selected_collaborate_persons = []
            if collaborate_departments:
                all_collaborate_processors = []
                for dept in collaborate_departments:
                    processors = db.get_department_processors(dept)
                    all_collaborate_processors.extend([f"{p['real_name']} ({dept})" for p in processors])
                
                if all_collaborate_processors:
                    selected_collaborate_persons = st.multiselect(
                        "协同处理人 (可多选)",
                        all_collaborate_processors,
                        default=[],
                        help="请选择协同处理人员"
                    )
                else:
                    st.warning("所选协同部门暂无处理人")
        
        # 协同意见
        collaborate_comments = st.text_area(
            "协同意见",
            placeholder="请输入协同处理的原因和要求...",
            height=100
        )
        
        # 协同派单按钮
        if st.button("协同派单", type="primary"):
            # 防重复提交：检查是否已经在处理中
            if 'collaborate_processing' not in st.session_state:
                st.session_state.collaborate_processing = False
            
            if st.session_state.collaborate_processing:
                st.warning("正在处理中，请勿重复点击...")
                return
            
            if collaborate_departments and collaborate_comments.strip():
                # 设置处理中状态
                st.session_state.collaborate_processing = True
                
                # 提取协同处理人姓名（去掉部门信息）
                collaborate_person_names = [p.split(' (')[0] for p in selected_collaborate_persons] if selected_collaborate_persons else []
                
                if collaborate_work_order(problem['id'], current_department, collaborate_departments, user_info['real_name'], collaborate_comments, collaborate_person_names):
                    st.success("协同派单成功！工单状态已调整为处理中，已设置多部门处理")
                    # 重置处理状态
                    st.session_state.collaborate_processing = False
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    # 失败时重置处理状态
                    st.session_state.collaborate_processing = False
                    st.error("协同派单失败，请重试")
            else:
                st.error("请选择协同部门并填写协同意见")

def render_replied_operation(problem: Dict, user_info: Dict):
    """渲染已处理回复工单操作"""
    operation_type = st.selectbox(
        "操作类型",
        ["继续处理", "转派工单"],
        help="请选择要执行的操作"
    )
    
    if operation_type == "继续处理":
        st.write("**操作类型:** 继续处理")
        
        # 继续处理意见
        processing_comments = st.text_area(
            "继续处理意见",
            placeholder="请输入继续处理意见...",
            height=100
        )
        
        # 确认继续处理按钮
        if st.button("确认继续处理", type="primary"):
            if processing_comments.strip():
                if accept_work_order(problem['id'], user_info['real_name'], processing_comments):
                    st.success("继续处理成功！")
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
                else:
                    st.error("继续处理失败，请重试")
            else:
                st.error("请填写继续处理意见")
    
    else:  # 转派工单
        st.write("**操作类型:** 转派工单")
        
        # 获取所有部门
        departments = get_all_departments()
        
        # 使用列布局将转派部门和转派处理人放在同一行
        col1, col2 = st.columns(2)
        
        with col1:
            # 转派部门选择（可多选）
            selected_departments = st.multiselect(
                "转派部门 (可多选)",
                departments,
                default=[],
                help="请选择转派部门(可多选)"
            )
        
        with col2:
            # 转派处理人选择（可多选）
            selected_persons = []
            if selected_departments:
                all_processors = []
                for dept in selected_departments:
                    processors = db.get_department_processors(dept)
                    all_processors.extend([f"{p['real_name']} ({dept})" for p in processors])
                
                if all_processors:
                    selected_persons = st.multiselect(
                        "转派处理人 (可多选)",
                        all_processors,
                        default=[],
                        help="请选择转派处理人"
                    )
                else:
                    st.warning("所选部门暂无处理人")
        
        # 转派意见
        reassign_comments = st.text_area(
            "转派意见",
            placeholder="请输入转派意见...",
            height=100
        )
        
        # 确认转派按钮
        if st.button("确认转派", type="primary"):
            if selected_departments and selected_persons:
                # 提取处理人姓名（去掉部门信息）
                person_names = [p.split(' (')[0] for p in selected_persons]
                
                if reassign_work_order(problem['id'], selected_departments, person_names, user_info['real_name'], reassign_comments):
                    st.success("工单转派成功！")
                    # 自动跳转回工单调度首页
                    st.switch_page("pages/工单调度.py")
            else:
                    st.error("转派失败，请重试")

def render_resolved_operation(problem: Dict, user_info: Dict):
    """渲染已办结工单操作"""
    st.write("**操作类型:** 重新开启工单")
    
    st.info("工单已办结，如需重新处理，请点击下方按钮重新开启工单。")
    
    # 重新开启按钮
    if st.button("重新开启工单", type="primary"):
        if reopen_work_order(problem['id'], user_info['real_name']):
            st.success("工单已重新开启！")
            # 自动跳转回工单调度首页
            st.switch_page("pages/工单调度.py")
        else:
            st.error("重新开启失败，请重试")

def render_work_order_dashboard(user_info: Dict):
    """渲染工单管理仪表板"""
    st.markdown('<h1 class="main-header">📋 工单管理</h1>', unsafe_allow_html=True)
    
    # 获取筛选选项
    statuses = get_all_statuses()
    categories = ["全部分类"] + get_all_categories()
    departments = ["全部部门"] + get_all_departments()
    
    # 筛选控件
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        status_filter = st.selectbox("状态筛选", statuses, index=0)
    
    with col2:
        category_filter = st.selectbox("分类筛选", categories, index=0)
    
    with col3:
        department_filter = st.selectbox("部门筛选", departments, index=0)
    
    # col4 已移除（原为新建工单功能）
    
    # 获取筛选后的工单
    work_orders = get_filtered_work_orders(user_info, status_filter, category_filter, department_filter)
    
    # 统计信息
    stats = db.get_work_order_statistics(user_info)
    
    # 统计卡片
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #ffc107;">
            <div class="metric-number">{stats['待处理']}</div>
            <div class="metric-label">待处理</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #17a2b8;">
            <div class="metric-number">{stats['已派发']}</div>
            <div class="metric-label">已派发</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #28a745;">
            <div class="metric-number">{stats['处理中']}</div>
            <div class="metric-label">处理中</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #6f42c1;">
            <div class="metric-number">{stats['已处理回复']}</div>
            <div class="metric-label">已处理回复</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col5:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #dc3545;">
            <div class="metric-number">{stats['已办结']}</div>
            <div class="metric-label">已办结</div>
        </div>
        """, unsafe_allow_html=True)
    
    # 检查是否有选中的工单
    selected_work_order = st.session_state.get('selected_work_order')
    
    if selected_work_order:
        # 显示选中的工单详情和操作
        problem = next((p for p in work_orders if p['id'] == selected_work_order), None)
        if problem:
            render_work_order_detail(problem)
            render_work_order_operation(problem, user_info)
            
            if st.button("返回工单列表"):
                st.session_state.selected_work_order = None
                st.rerun()
        else:
            st.error("工单不存在")
            st.session_state.selected_work_order = None
            st.rerun()
    else:
        # 工单表格
        if work_orders:
            # 准备表格数据
            table_data = []
            for problem in work_orders:
                # 根据状态确定可用的操作按钮
                status = problem.get('status', '待处理')
                user_role = user_info['role']
                user_name = user_info['real_name']
                user_department = user_info.get('department', '')
                
                # 重新计算显示状态，确保与统计逻辑一致
                display_status = status
                processing_unit = problem.get('processing_unit', '')
                is_processing = problem.get('is_processing', False)
                is_resolved = problem.get('is_resolved', False)
                processing_records_count = problem.get('processing_records_count', 0)
                
                # 使用与数据库管理器相同的状态判断逻辑
                if is_resolved:
                    display_status = "已办结"
                elif status == '已处理回复':
                    display_status = "已处理回复"
                else:
                    # 优先检测驳回工单：如果工单被驳回到调度中心，应显示为待处理状态
                    is_rejected_to_dispatch = False
                    if status == '待处理' and processing_unit == '调度中心' and processing_records_count > 0:
                        # 检查是否为驳回工单
                        is_rejected_to_dispatch = is_rejected_work_order(problem['id'])
                    
                    if is_rejected_to_dispatch:
                        display_status = "待处理"  # 驳回工单显示为待处理
                    elif is_processing or (processing_records_count > 0 and status != '待处理'):
                        display_status = "处理中"
                    elif status == '已派发' or (processing_unit and processing_unit.strip() and status != '待处理'):
                        display_status = "已派发"
                    else:
                        display_status = "待处理"
                
                # 检查用户是否有权限操作此工单
                can_operate = False
                
                if user_role == 'admin':
                    # admin可以操作所有工单
                    can_operate = True
                elif user_department == '调度中心':
                    # 调度中心用户：只能操作当前处理部门为调度中心或为空的工单
                    current_processing_unit = problem.get('processing_unit', '')
                    can_operate = (current_processing_unit == '调度中心' or 
                                  current_processing_unit == '' or 
                                  current_processing_unit is None)
                else:
                    # 非调度中心用户：只能操作当前处理部门或首响部门为自己部门的工单
                    current_processing_unit = problem.get('processing_unit', '')
                    response_department = problem.get('response_department', '')
                    can_operate = (current_processing_unit == user_department or 
                                  response_department == user_department)
                
                # 确定操作按钮
                actions = []
                if display_status == '待处理' and user_role == 'admin':
                    actions.append("调度")
                elif display_status == '已派发' and can_operate:
                    actions.append("接单")
                    actions.append("驳回")
                    actions.append("转派")
                elif display_status == '处理中' and can_operate:
                    actions.append("回复处理")
                    actions.append("标记已处理")
                    actions.append("转派")
                elif display_status == '已处理回复' and can_operate:
                    actions.append("继续处理")
                    actions.append("转派")
                    if user_role == 'admin' or user_department == '调度中心':
                        actions.append("已办结")
                elif display_status == '已办结' and user_role == 'admin':
                    actions.append("重新开启")
                
                # 优先级显示
                priority = problem.get('priority', '普通')
                priority_display = {
                    '高': '🔴 高',
                    '中': '🟡 中', 
                    '低': '🟢 低',
                    '普通': '🟡 中'
                }.get(priority, '🟡 中')
                
                table_data.append({
                    '工单号': f"WT{str(problem['id']).zfill(5)}",
                    '标题': problem['title'],
                    '分类': problem['category'],
                    '提交人': problem['author'],
                    '提交部门': problem.get('department', '未指定'),
                    '首响部门': problem.get('response_department', '未指定'),
                    '提交时间': problem.get('created_at', '未设置'),
                    '优先级': priority_display,
                    '状态': display_status,
                    '当前处理部门': problem.get('processing_unit', '-'),
                    "操作": ' | '.join(actions) if actions else '无'
                })
            
            # 创建DataFrame并显示表格
            df = pd.DataFrame(table_data)
            
            # 设置表格样式
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "工单号": st.column_config.TextColumn("工单号", width="medium"),
                    "标题": st.column_config.TextColumn("标题", width="large"),
                    "分类": st.column_config.TextColumn("分类", width="small"),
                    "提交人": st.column_config.TextColumn("提交人", width="small"),
                    "提交部门": st.column_config.TextColumn("问题提交部门", width="small"),
                    "首响部门": st.column_config.TextColumn("首响部门", width="small"),
                    "提交时间": st.column_config.TextColumn("提交时间", width="medium"),
                    "优先级": st.column_config.TextColumn("优先级", width="small"),
                    "状态": st.column_config.TextColumn("状态", width="small"),
                    "当前处理部门": st.column_config.TextColumn("当前处理部门", width="small"),
                    "操作": st.column_config.TextColumn("操作", width="medium")
                }
            )
            
            # 添加操作按钮
            st.markdown("### 工单操作")
            
            # 获取用户可操作的工单列表
            operable_work_orders = get_operable_work_orders(user_info)
            
            if operable_work_orders:
                st.info(f"您当前可以操作 {len(operable_work_orders)} 个工单")
                
                # 准备单选框选项
                work_order_options = []
                work_order_details = {}
                
                for problem in operable_work_orders:
                    work_order_id = f"WT{str(problem['id']).zfill(5)}"
                    title = problem.get('title', '无标题')
                    category = problem.get('category', '未分类')
                    status = problem.get('status', '待处理')
                
                    # 重新计算显示状态
                    display_status = status
                    processing_unit = problem.get('processing_unit', '')
                    is_processing = problem.get('is_processing', False)
                    is_resolved = problem.get('is_resolved', False)
                    processing_records_count = problem.get('processing_records_count', 0)
                
                    # 使用与数据库管理器相同的状态判断逻辑
                    if is_resolved:
                        display_status = "已办结"
                    elif status == '已处理回复':
                        display_status = "已处理回复"
                    else:
                        # 优先检测驳回工单：如果工单被驳回到调度中心，应显示为待处理状态
                        is_rejected_to_dispatch = False
                        if status == '待处理' and processing_unit == '调度中心' and processing_records_count > 0:
                            # 检查是否为驳回工单
                            is_rejected_to_dispatch = is_rejected_work_order(problem['id'])
                        
                        if is_rejected_to_dispatch:
                            display_status = "待处理"  # 驳回工单显示为待处理
                        elif is_processing or (processing_records_count > 0 and status != '待处理'):
                            display_status = "处理中"
                        elif status == '已派发' or (processing_unit and processing_unit.strip() and status != '待处理'):
                            display_status = "已派发"
                        else:
                            display_status = "待处理"
                    
                    # 获取提交时间
                    created_at = problem.get('created_at', '未设置')
                    # 格式化时间显示
                    if created_at != '未设置':
                        try:
                            # 如果是datetime对象，转换为字符串
                            if hasattr(created_at, 'strftime'):
                                created_at = created_at.strftime('%Y年%m月%d日 %H:%M')
                            else:
                                # 如果是字符串，尝试解析并格式化
                                from datetime import datetime
                                dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                                created_at = dt.strftime('%Y年%m月%d日 %H:%M')
                        except:
                            created_at = str(created_at)
                    
                    # 获取提交人
                    author = problem.get('author', '未知')
                    
                    # 获取上一流程部门（当前处理部门）
                    previous_department = get_previous_department(problem['id'])
                    
                    # 判断是否协作工单（使用新的逻辑）
                    is_collaboration = is_collaboration_work_order(problem['id'])
                    collaboration_text = "是" if is_collaboration else "否"
                    
                    # 判断是否为驳回工单
                    is_rejected = False
                    reject_info = ""
                    if display_status == "待处理" and processing_unit == "调度中心":
                        # 检查是否有驳回记录
                        is_rejected = is_rejected_work_order(problem['id'])
                        if is_rejected:
                            reject_info = " | ⚠️ 驳回工单"
                    
                    # 构建选项文本
                    option_text = f"{work_order_id} - {title} | 分类:{category} | 状态:{display_status} | 提交时间:{created_at} | 提交人:{author} | 上一流程部门:{previous_department} | 协作工单:{collaboration_text}{reject_info}"
                    
                    work_order_options.append(option_text)
                    work_order_details[option_text] = problem['id']
                
                # 显示单选框
                if work_order_options:
                    # 添加一个"请选择"选项作为默认值
                    work_order_options_with_default = ["请选择要操作的工单"] + work_order_options
                    
                    selected_option = st.radio(
                        "请选择要操作的工单：",
                        work_order_options_with_default,
                        help="点击选项进入具体操作界面"
                    )
                    
                    # 只有当用户选择了具体工单时才跳转
                    if selected_option and selected_option != "请选择要操作的工单":
                        selected_work_order_id = work_order_details[selected_option]
                        st.session_state.selected_work_order = selected_work_order_id
                        st.rerun()
            else:
                st.info("您当前没有可操作的工单")
            
            # 显示用户权限信息
            st.info(f"当前用户: {user_info['real_name']} ({user_info['role']}) - 部门: {user_info.get('department', '未设置')}")
            
            # 删除系统维护区域，不再需要手动修复功能
            # if user_info.get('department') == '调度中心':
            #     st.subheader("🔧 系统维护")
            #     
            #     if st.button("🔄 修复协同工单状态", help="检查并修复所有协同工单的流转状态"):
            #         with st.spinner("正在检查和修复协同工单状态..."):
            #             fixed_count = check_and_fix_collaborative_work_orders()
            #             if fixed_count > 0:
            #                 st.success(f"已成功修复 {fixed_count} 个协同工单状态！")
            #                 st.info("工单现在应该能正确流转至调度中心，请刷新页面查看效果。")
            #                 st.rerun()
            #             else:
            #                 st.info("所有协同工单状态正常，无需修复。")
        else:
            st.info("暂无相关工单")

@require_role(['processor', 'manager', 'admin'])
def main():
    """主函数"""
    # 渲染权限控制导航侧边栏
    render_navigation_sidebar()
    
    # 检查用户权限
    user_info = check_user_permission()
    
    # 删除自动修复功能，不再需要
    # fixed_count = check_and_fix_collaborative_work_orders()
    # if fixed_count > 0:
    #     st.info(f"系统已自动修复 {fixed_count} 个协同工单状态，确保工单正确流转至调度中心")
    
    # 渲染工单管理仪表板
    render_work_order_dashboard(user_info)

def check_all_collaborative_departments_processed(problem_id):
    """检查协同工单的所有部门是否都已处理回复"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取所有协同部门（排除调度中心）
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

if __name__ == "__main__":
    main()
