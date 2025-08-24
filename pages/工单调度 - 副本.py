import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
from typing import List, Dict, Optional
import logging

# 导入数据库管理器和认证管理器
from db_manager import db
from auth_manager import auth_manager

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
    
    .status-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }
    
    .status-pending {
        border-left: 4px solid #ffc107;
    }
    
    .status-assigned {
        border-left: 4px solid #17a2b8;
    }
    
    .status-processing {
        border-left: 4px solid #28a745;
    }
    
    .status-replied {
        border-left: 4px solid #6f42c1;
    }
    
    .status-resolved {
        border-left: 4px solid #dc3545;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin: 10px 0;
    }
    
    .metric-number {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 5px;
    }
    
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    
    .action-button {
        margin: 5px;
        padding: 8px 16px;
        border-radius: 5px;
        border: none;
        cursor: pointer;
        font-size: 0.9rem;
        transition: all 0.3s ease;
    }
    
    .btn-primary {
        background-color: #007bff;
        color: white;
    }
    
    .btn-success {
        background-color: #28a745;
        color: white;
    }
    
    .btn-warning {
        background-color: #ffc107;
        color: #212529;
    }
    
    .btn-danger {
        background-color: #dc3545;
        color: white;
    }
    
    .btn-info {
        background-color: #17a2b8;
        color: white;
    }
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

# 定义状态流转规则
STATUS_FLOW = {
    WORK_ORDER_STATUS['PENDING']: [WORK_ORDER_STATUS['ASSIGNED']],
    WORK_ORDER_STATUS['ASSIGNED']: [WORK_ORDER_STATUS['PROCESSING']],
    WORK_ORDER_STATUS['PROCESSING']: [WORK_ORDER_STATUS['REPLIED']],
    WORK_ORDER_STATUS['REPLIED']: [WORK_ORDER_STATUS['RESOLVED']],
    WORK_ORDER_STATUS['RESOLVED']: []  # 最终状态
}

def check_user_permission():
    """检查用户是否有权限访问工单调度页面"""
    user_info = st.session_state.get('user_info')
    if not user_info:
        st.error("请先登录")
        st.stop()
    
    user_role = user_info['role']
    if user_role == 'user':
        st.error("您没有权限访问工单调度页面")
        st.stop()
    
    return user_info

def assign_work_order(problem_id: int, assigned_department: str, assigned_person: str, operator: str) -> bool:
    """分配工单"""
    try:
        # 更新工单状态为已派发
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['ASSIGNED'], operator, f"工单已派发给{assigned_department}-{assigned_person}")
        
        if success:
            # 更新工单处理人
            db.update_problem_processor(problem_id, assigned_person, assigned_department)
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单派发给{assigned_department}-{assigned_person}",
                department=assigned_department,
                assigned_to=assigned_person
            )
            return True
        return False
    except Exception as e:
        st.error(f"分配工单失败: {e}")
        return False

def accept_work_order(problem_id: int, processor: str) -> bool:
    """接单处理"""
    try:
        # 获取用户信息
        user_department = st.session_state.user_info.get('department', '')
        
        # 更新工单状态为处理中
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['PROCESSING'], processor, "已接单开始处理")
        
        if success:
            # 更新处理人和处理部门
            db.update_problem_processor(problem_id, processor, user_department)
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=processor,
                measure="接单开始处理",
                department=user_department
            )
            return True
        return False
    except Exception as e:
        st.error(f"接单失败: {e}")
        return False

def reply_work_order(problem_id: int, processor: str, reply_content: str) -> bool:
    """回复处理意见"""
    try:
        # 添加处理记录
        success = db.add_processing_record(
            problem_id=problem_id,
            processor=processor,
            measure=reply_content,
            department=st.session_state.user_info.get('department', '')
        )
        return success
    except Exception as e:
        st.error(f"回复失败: {e}")
        return False

def mark_as_processed(problem_id: int, processor: str) -> bool:
    """标记为已处理"""
    try:
        # 更新工单状态为已处理回复
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['REPLIED'], processor, "已处理完成")
        
        if success:
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=processor,
                measure="标记为已处理",
                department=st.session_state.user_info.get('department', '')
            )
            return True
        return False
    except Exception as e:
        st.error(f"标记失败: {e}")
        return False

def close_work_order(problem_id: int, operator: str) -> bool:
    """关闭工单"""
    try:
        # 更新工单状态为已办结
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['RESOLVED'], operator, "工单已办结")
        
        if success:
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure="工单已办结",
                department=st.session_state.user_info.get('department', '')
            )
            return True
        return False
    except Exception as e:
        st.error(f"关闭工单失败: {e}")
        return False

def close_work_order_with_comment(problem_id: int, operator: str, close_comment: str) -> bool:
    """关闭工单（带办结意见）"""
    try:
        # 更新工单状态为已办结
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['RESOLVED'], operator, f"工单已办结，办结意见：{close_comment}")
        
        if success:
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单已办结，办结意见：{close_comment}",
                department=st.session_state.user_info.get('department', '')
            )
            return True
        return False
    except Exception as e:
        st.error(f"关闭工单失败: {e}")
        return False

def reassign_work_order(problem_id: int, new_department: str, new_person: str, operator: str, reason: str) -> bool:
    """转派工单"""
    try:
        # 更新工单状态为已派发
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['ASSIGNED'], operator, f"工单转派给{new_department}-{new_person}，原因：{reason}")
        
        if success:
            # 更新工单处理人
            db.update_problem_processor(problem_id, new_person, new_department)
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单转派给{new_department}-{new_person}，原因：{reason}",
                department=new_department,
                assigned_to=new_person
            )
            return True
        return False
    except Exception as e:
        st.error(f"转派工单失败: {e}")
        return False

def reject_work_order(problem_id: int, operator: str, reject_reason: str) -> bool:
    """驳回工单"""
    try:
        # 更新工单状态为待处理（流转回上一流程）
        success = db.update_problem_status(problem_id, WORK_ORDER_STATUS['PENDING'], operator, f"工单被驳回，原因：{reject_reason}")
        
        if success:
            # 清空处理人和处理部门
            db.update_problem_processor(problem_id, None, None)
            
            # 添加处理记录
            db.add_processing_record(
                problem_id=problem_id,
                processor=operator,
                measure=f"工单驳回，原因：{reject_reason}",
                department=st.session_state.user_info.get('department', '')
            )
            return True
        return False
    except Exception as e:
        st.error(f"驳回工单失败: {e}")
        return False

def get_user_work_orders(user_info: Dict) -> Dict[str, List[Dict]]:
    """获取用户相关的工单"""
    # 使用新的数据库方法获取工单
    filtered_orders = {
        'pending': db.get_work_orders_by_status(WORK_ORDER_STATUS['PENDING'], user_info),
        'assigned': db.get_work_orders_by_status(WORK_ORDER_STATUS['ASSIGNED'], user_info),
        'processing': db.get_work_orders_by_status(WORK_ORDER_STATUS['PROCESSING'], user_info),
        'replied': db.get_work_orders_by_status(WORK_ORDER_STATUS['REPLIED'], user_info),
        'resolved': db.get_work_orders_by_status(WORK_ORDER_STATUS['RESOLVED'], user_info)
    }
    
    return filtered_orders

def render_work_order_card(problem: Dict, user_info: Dict):
    """渲染工单卡片"""
    status = problem.get('status', '待处理')
    status_class = f"status-{status.lower().replace(' ', '-')}"
    
    with st.container():
        st.markdown(f"""
        <div class="status-card {status_class}">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h4 style="margin: 0; color: #1f77b4;">{problem['title']}</h4>
                    <p style="margin: 5px 0; color: #666;">工单号: {problem.get('work_order', f'NO.{problem["id"]:08d}')}</p>
                    <p style="margin: 5px 0; color: #666;">分类: {problem['category']}</p>
                    <p style="margin: 5px 0; color: #666;">提交人: {problem['author']}</p>
                    <p style="margin: 5px 0; color: #666;">提交时间: {problem['created_at']}</p>
                    <p style="margin: 5px 0; color: #666;">提交部门: {problem.get('department', '未指定')}</p>
                    <p style="margin: 5px 0; color: #666;">首响部门: {problem.get('response_department', '未指定')}</p>
                    <p style="margin: 5px 0; color: #666;">处理人: {problem.get('processing_person', '未分配')}</p>
                    <p style="margin: 5px 0; color: #666;">处理部门: {problem.get('processing_unit', '未指定')}</p>
                </div>
                <div style="text-align: right;">
                    <span style="padding: 5px 10px; border-radius: 15px; background-color: #f8f9fa; color: #495057;">
                        {status}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 操作按钮 - 增加更多列
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            if st.button("查看详情", key=f"view_{problem['id']}"):
                st.session_state.selected_problem = problem['id']
                st.rerun()
        
        # 根据状态和权限显示不同的操作按钮
        user_role = user_info['role']
        user_name = user_info['real_name']
        user_department = user_info.get('department', '')
        
        # 检查用户是否有权限操作此工单
        can_operate = (
            user_role == 'admin' or 
            problem.get('processing_person') == user_name or
            problem.get('response_department') == user_department or
            problem.get('processing_unit') == user_department
        )
        
        if status == WORK_ORDER_STATUS['PENDING'] and user_role == 'admin':
            with col2:
                if st.button("派发工单", key=f"assign_{problem['id']}"):
                    st.session_state.assign_problem = problem['id']
                    st.rerun()
        
        elif status == WORK_ORDER_STATUS['ASSIGNED']:
            if can_operate:
                with col2:
                    if st.button("接单处理", key=f"accept_{problem['id']}"):
                        if accept_work_order(problem['id'], user_name):
                            st.success("接单成功")
                            st.rerun()
                with col3:
                    if st.button("转派工单", key=f"reassign_assigned_{problem['id']}"):
                        st.session_state.reassign_problem = problem['id']
                        st.rerun()
        
        elif status == WORK_ORDER_STATUS['PROCESSING']:
            if can_operate:
                with col2:
                    if st.button("回复处理", key=f"reply_{problem['id']}"):
                        st.session_state.reply_problem = problem['id']
                        st.rerun()
                with col3:
                    if st.button("标记已处理", key=f"mark_{problem['id']}"):
                        if mark_as_processed(problem['id'], user_name):
                            st.success("标记成功")
                            st.rerun()
                with col4:
                    if st.button("转派工单", key=f"reassign_{problem['id']}"):
                        st.session_state.reassign_problem = problem['id']
                        st.rerun()
        
        elif status == WORK_ORDER_STATUS['REPLIED']:
            if can_operate:
                with col2:
                    if st.button("继续处理", key=f"continue_{problem['id']}"):
                        st.session_state.reply_problem = problem['id']
                        st.rerun()
                with col3:
                    if st.button("转派工单", key=f"reassign_replied_{problem['id']}"):
                        st.session_state.reassign_problem = problem['id']
                        st.rerun()
            if user_role == 'admin':
                with col4:
                    if st.button("关闭工单", key=f"close_{problem['id']}"):
                        st.session_state.close_problem = problem['id']
                        st.rerun()
        
        elif status == WORK_ORDER_STATUS['RESOLVED']:
            if user_role == 'admin':
                with col2:
                    if st.button("重新开启", key=f"reopen_{problem['id']}"):
                        if db.update_problem_status(problem['id'], WORK_ORDER_STATUS['PROCESSING'], user_name, "工单重新开启"):
                            st.success("工单已重新开启")
                            st.rerun()
        
        # 显示权限信息（调试用）
        if st.session_state.get('debug_mode', False):
            st.text(f"调试信息 - 用户权限: {can_operate}, 角色: {user_role}, 部门: {user_department}")
            st.text(f"工单信息 - 处理人: {problem.get('processing_person')}, 首响部门: {problem.get('response_department')}, 处理部门: {problem.get('processing_unit')}")

def render_assign_dialog(problem_id: int, user_info: Dict):
    """渲染派发工单对话框"""
    st.subheader("派发工单")
    
    # 获取所有部门
    departments = db.get_all_departments()
    
    col1, col2 = st.columns(2)
    
    with col1:
        selected_department = st.selectbox("选择处理部门", departments)
    
    with col2:
        # 获取部门处理人
        processors = db.get_department_processors(selected_department)
        processor_names = [p['real_name'] for p in processors]
        selected_processor = st.selectbox("选择处理人", processor_names)
    
    col3, col4 = st.columns(2)
    
    with col3:
        if st.button("确认派发"):
            if assign_work_order(problem_id, selected_department, selected_processor, user_info['real_name']):
                st.success("工单派发成功")
                st.session_state.assign_problem = None
                st.rerun()
    
    with col4:
        if st.button("取消"):
            st.session_state.assign_problem = None
            st.rerun()

def render_reply_dialog(problem_id: int, user_info: Dict):
    """渲染回复处理对话框"""
    st.subheader("回复处理意见")
    
    reply_content = st.text_area("处理意见", height=150)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("提交回复"):
            if reply_content.strip():
                if reply_work_order(problem_id, user_info['real_name'], reply_content):
                    st.success("回复提交成功")
                    st.session_state.reply_problem = None
                    st.rerun()
            else:
                st.error("请输入处理意见")
    
    with col2:
        if st.button("取消"):
            st.session_state.reply_problem = None
            st.rerun()

def render_reassign_dialog(problem_id: int, user_info: Dict):
    """渲染转派工单对话框"""
    st.subheader("转派工单")
    
    # 获取所有部门
    departments = db.get_all_departments()
    
    col1, col2 = st.columns(2)
    
    with col1:
        selected_department = st.selectbox("选择新处理部门", departments, key="reassign_dept")
    
    with col2:
        # 获取部门处理人
        processors = db.get_department_processors(selected_department)
        processor_names = [p['real_name'] for p in processors]
        selected_processor = st.selectbox("选择新处理人", processor_names, key="reassign_processor")
    
    # 转派原因
    reason = st.text_area("转派原因", height=100)
    
    col3, col4 = st.columns(2)
    
    with col3:
        if st.button("确认转派", key="confirm_reassign"):
            if reason.strip():
                if reassign_work_order(problem_id, selected_department, selected_processor, user_info['real_name'], reason):
                    st.success("工单转派成功")
                    st.session_state.reassign_problem = None
                    st.rerun()
            else:
                st.error("请输入转派原因")
    
    with col4:
        if st.button("取消", key="cancel_reassign"):
            st.session_state.reassign_problem = None
            st.rerun()

def render_reject_dialog(problem_id: int, user_info: Dict):
    """渲染驳回工单对话框"""
    st.subheader("驳回工单")
    
    reject_reason = st.text_area("驳回原因", height=150, placeholder="请详细说明驳回原因...")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("确认驳回"):
            if reject_reason.strip():
                if reject_work_order(problem_id, user_info['real_name'], reject_reason):
                    st.success("工单驳回成功")
                    st.session_state.reject_problem = None
                    st.rerun()
            else:
                st.error("请输入驳回原因")
    
    with col2:
        if st.button("取消"):
            st.session_state.reject_problem = None
            st.rerun()

def render_close_dialog(problem_id: int, user_info: Dict):
    """渲染关闭工单对话框"""
    st.subheader("工单办结")
    
    close_comment = st.text_area("办结处理意见", height=150, placeholder="请详细说明办结处理意见...")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("确认办结"):
            if close_comment.strip():
                if close_work_order_with_comment(problem_id, user_info['real_name'], close_comment):
                    st.success("工单已办结")
                    st.session_state.close_problem = None
                    st.rerun()
            else:
                st.error("请输入办结处理意见")
    
    with col2:
        if st.button("取消"):
            st.session_state.close_problem = None
            st.rerun()

def render_work_order_details(problem_id: int):
    """渲染工单详情"""
    problem = db.get_problem_by_id(problem_id)
    if not problem:
        st.error("工单不存在")
        return
    
    st.subheader(f"工单详情 - {problem['title']}")
    
    # 工单基本信息
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"**工单号:** {problem.get('work_order', f'NO.{problem["id"]:08d}')}")
        st.write(f"**分类:** {problem['category']}")
        st.write(f"**提交人:** {problem['author']}")
        st.write(f"**提交时间:** {problem['created_at']}")
        st.write(f"**状态:** {problem['status']}")
    
    with col2:
        st.write(f"**部门:** {problem.get('department', '未指定')}")
        st.write(f"**处理人:** {problem.get('processing_person', '未分配')}")
        st.write(f"**优先级:** {problem.get('priority', '普通')}")
        st.write(f"**联系方式:** {problem.get('contact_info', '无')}")
    
    # 问题描述
    st.subheader("问题描述")
    st.write(problem['description'])
    
    # 处理记录
    st.subheader("处理记录")
    processing_records = db.get_processing_records(problem_id)
    
    if processing_records:
        for record in processing_records:
            with st.expander(f"{record['created_at']} - {record['processor']}"):
                st.write(f"**处理措施:** {record['measure']}")
                if record.get('department'):
                    st.write(f"**部门:** {record['department']}")
                if record.get('assigned_to'):
                    st.write(f"**分配给:** {record['assigned_to']}")
    else:
        st.info("暂无处理记录")
    
    # 状态变更记录
    st.subheader("状态变更记录")
    status_logs = db.get_status_logs(problem_id)
    
    if status_logs:
        for log in status_logs:
            with st.expander(f"{log['created_at']} - {log['operator']}"):
                st.write(f"**状态变更:** {log['old_status']} → {log['new_status']}")
                if log.get('comment'):
                    st.write(f"**备注:** {log['comment']}")
    else:
        st.info("暂无状态变更记录")
    
    if st.button("返回工单列表"):
        st.session_state.selected_problem = None
        st.rerun()

def render_work_order_table(problems: List[Dict], user_info: Dict):
    """以表格形式渲染工单列表"""
    if not problems:
        st.info("暂无相关工单")
        return
    
    # 准备表格数据
    table_data = []
    for problem in problems:
        # 根据状态确定可用的操作按钮
        status = problem.get('status', '待处理')
        user_role = user_info['role']
        user_name = user_info['real_name']
        user_department = user_info.get('department', '')
        
        # 检查用户是否有权限操作此工单
        can_operate = (
            user_role == 'admin' or 
            problem.get('processing_person') == user_name or
            problem.get('response_department') == user_department or
            problem.get('processing_unit') == user_department
        )
        
        # 确定操作按钮
        actions = []
        if status == '待处理' and user_role == 'admin':
            actions.append("派发")
        elif status == '已派发' and can_operate:
            actions.append("接单")
            actions.append("驳回")
            actions.append("转派")
        elif status == '处理中' and can_operate:
            actions.append("回复处理")
            actions.append("标记已处理")
            actions.append("转派")
        elif status == '已处理回复' and can_operate:
            actions.append("继续处理")
            actions.append("转派")
            # 为调度中心处理人或admin权限的人员添加已办结操作
            if user_role == 'admin' or user_department == '调度中心':
                actions.append("已办结")
        elif status == '已办结' and user_role == 'admin':
            actions.append("重新开启")
        
        table_data.append({
            '工单号': problem.get('work_order', f'NO.{problem["id"]:08d}'),
            '标题': problem['title'],
            '分类': problem['category'],
            '提交人': problem['author'],
            '提交时间': problem['created_at'],
            '提交部门': problem.get('department', '未指定'),
            '首响部门': problem.get('response_department', '未指定'),
            '处理人': problem.get('processing_person', '未分配'),
            '处理部门': problem.get('processing_unit', '未指定'),
            '状态': status,
            '操作': ' | '.join(actions) if actions else '无'
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
            "提交时间": st.column_config.TextColumn("提交时间", width="medium"),
            "提交部门": st.column_config.TextColumn("提交部门", width="small"),
            "首响部门": st.column_config.TextColumn("首响部门", width="small"),
            "处理人": st.column_config.TextColumn("处理人", width="small"),
            "处理部门": st.column_config.TextColumn("处理部门", width="small"),
            "状态": st.column_config.TextColumn("状态", width="small"),
            "操作": st.column_config.TextColumn("操作", width="medium")
        }
    )
    
    # 为每个工单添加操作按钮
    st.subheader("工单操作")
    
    for i, problem in enumerate(problems):
        with st.expander(f"工单 {problem.get('work_order', f'NO.{problem["id"]:08d}')} - {problem['title']}"):
            col1, col2, col3, col4, col5 = st.columns(5)
            
            status = problem.get('status', '待处理')
            user_role = user_info['role']
            user_name = user_info['real_name']
            user_department = user_info.get('department', '')
            
            # 检查用户是否有权限操作此工单
            can_operate = (
                user_role == 'admin' or 
                problem.get('processing_person') == user_name or
                problem.get('response_department') == user_department or
                problem.get('processing_unit') == user_department
            )
            
            with col1:
                if st.button("查看详情", key=f"view_{problem['id']}"):
                    st.session_state.selected_problem = problem['id']
                    st.rerun()
            
            # 根据状态显示不同的操作按钮
            if status == '待处理' and user_role == 'admin':
                with col2:
                    if st.button("派发工单", key=f"assign_{problem['id']}"):
                        st.session_state.assign_problem = problem['id']
                        st.rerun()
            
            elif status == '已派发' and can_operate:
                with col2:
                    if st.button("接单", key=f"accept_{problem['id']}"):
                        if accept_work_order(problem['id'], user_name):
                            st.success("接单成功")
                            st.rerun()
                
                with col3:
                    if st.button("驳回", key=f"reject_{problem['id']}"):
                        st.session_state.reject_problem = problem['id']
                        st.rerun()
                
                with col4:
                    if st.button("转派", key=f"reassign_assigned_{problem['id']}"):
                        st.session_state.reassign_problem = problem['id']
                        st.rerun()
            
            elif status == '处理中' and can_operate:
                with col2:
                    if st.button("回复处理", key=f"reply_{problem['id']}"):
                        st.session_state.reply_problem = problem['id']
                        st.rerun()
                
                with col3:
                    if st.button("标记已处理", key=f"mark_{problem['id']}"):
                        if mark_as_processed(problem['id'], user_name):
                            st.success("标记成功")
                            st.rerun()
                
                with col4:
                    if st.button("转派", key=f"reassign_{problem['id']}"):
                        st.session_state.reassign_problem = problem['id']
                        st.rerun()
            
            elif status == '已处理回复' and can_operate:
                with col2:
                    if st.button("继续处理", key=f"continue_{problem['id']}"):
                        st.session_state.reply_problem = problem['id']
                        st.rerun()
                
                with col3:
                    if st.button("转派", key=f"reassign_replied_{problem['id']}"):
                        st.session_state.reassign_problem = problem['id']
                        st.rerun()
                
                # 为调度中心处理人或admin权限的人员添加已办结按钮
                if user_role == 'admin' or user_department == '调度中心':
                    with col4:
                        if st.button("已办结", key=f"close_{problem['id']}"):
                            st.session_state.close_problem = problem['id']
                            st.rerun()
            
            elif status == '已办结' and user_role == 'admin':
                with col2:
                    if st.button("重新开启", key=f"reopen_{problem['id']}"):
                        if db.update_problem_status(problem['id'], '处理中', user_name, "工单重新开启"):
                            st.success("工单已重新开启")
                            st.rerun()

def main():
    """主函数"""
    st.markdown('<h1 class="main-header">📋 工单调度中心</h1>', unsafe_allow_html=True)
    
    # 检查用户权限
    user_info = check_user_permission()
    
    # 添加调试模式开关
    with st.sidebar:
        st.markdown("---")
        debug_mode = st.checkbox("启用调试模式", value=st.session_state.get('debug_mode', False))
        st.session_state.debug_mode = debug_mode
        
        if debug_mode:
            st.info(f"当前用户: {user_info['real_name']}")
            st.info(f"用户角色: {user_info['role']}")
            st.info(f"用户部门: {user_info.get('department', '未设置')}")
    
    # 获取用户相关工单
    work_orders = get_user_work_orders(user_info)
    
    # 获取统计信息（实时更新）
    stats = db.get_work_order_statistics(user_info)
    
    # 统计信息
    st.subheader("📊 工单统计")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-number">{stats['待处理']}</div>
            <div class="metric-label">待处理</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-number">{stats['已派发']}</div>
            <div class="metric-label">已派发</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-number">{stats['处理中']}</div>
            <div class="metric-label">处理中</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-number">{stats['已处理回复']}</div>
            <div class="metric-label">已处理回复</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-number">{stats['已办结']}</div>
            <div class="metric-label">已办结</div>
        </div>
        """, unsafe_allow_html=True)
    
    # 检查是否有选中的工单详情
    if hasattr(st.session_state, 'selected_problem') and st.session_state.selected_problem:
        render_work_order_details(st.session_state.selected_problem)
        return
    
    # 检查是否有派发工单对话框
    if hasattr(st.session_state, 'assign_problem') and st.session_state.assign_problem:
        render_assign_dialog(st.session_state.assign_problem, user_info)
        return
    
    # 检查是否有回复处理对话框
    if hasattr(st.session_state, 'reply_problem') and st.session_state.reply_problem:
        render_reply_dialog(st.session_state.reply_problem, user_info)
        return
    
    # 检查是否有转派工单对话框
    if hasattr(st.session_state, 'reassign_problem') and st.session_state.reassign_problem:
        render_reassign_dialog(st.session_state.reassign_problem, user_info)
        return
    
    # 检查是否有驳回工单对话框
    if hasattr(st.session_state, 'reject_problem') and st.session_state.reject_problem:
        render_reject_dialog(st.session_state.reject_problem, user_info)
        return
    
    # 检查是否有关闭工单对话框
    if hasattr(st.session_state, 'close_problem') and st.session_state.close_problem:
        render_close_dialog(st.session_state.close_problem, user_info)
        return
    
    # 工单列表
    st.subheader("📋 工单列表")
    
    # 状态筛选
    status_filter = st.selectbox(
        "状态筛选",
        ["全部", "待处理", "已派发", "处理中", "已处理回复", "已办结"]
    )
    
    # 根据筛选显示工单
    if status_filter == "全部" or status_filter == "待处理":
        if work_orders['pending']:
            st.subheader("🟡 待处理工单")
            render_work_order_table(work_orders['pending'], user_info)
        elif status_filter == "待处理":
            st.info("暂无待处理工单")
    
    if status_filter == "全部" or status_filter == "已派发":
        if work_orders['assigned']:
            st.subheader("🔵 已派发工单")
            render_work_order_table(work_orders['assigned'], user_info)
        elif status_filter == "已派发":
            st.info("暂无已派发工单")
    
    if status_filter == "全部" or status_filter == "处理中":
        if work_orders['processing']:
            st.subheader("🟢 处理中工单")
            render_work_order_table(work_orders['processing'], user_info)
        elif status_filter == "处理中":
            st.info("暂无处理中工单")
    
    if status_filter == "全部" or status_filter == "已处理回复":
        if work_orders['replied']:
            st.subheader("🟣 已处理回复工单")
            render_work_order_table(work_orders['replied'], user_info)
        elif status_filter == "已处理回复":
            st.info("暂无已处理回复工单")
    
    if status_filter == "全部" or status_filter == "已办结":
        if work_orders['resolved']:
            st.subheader("🔴 已办结工单")
            render_work_order_table(work_orders['resolved'], user_info)
        elif status_filter == "已办结":
            st.info("暂无已办结工单")
    
    if status_filter == "全部" and not any(work_orders.values()):
        st.info("暂无相关工单")

if __name__ == "__main__":
    main() 