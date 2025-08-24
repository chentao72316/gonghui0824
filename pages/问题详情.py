import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from db_manager import db
from auth_manager import auth_manager
from export_manager import export_manager
from permission_control import require_auth, render_navigation_sidebar

# 页面配置
st.set_page_config(
    page_title="问题详情",
    page_icon="📋",
    layout="wide"
)

# 自定义CSS样式
st.markdown("""
<style>
    .problem-header {
        background: linear-gradient(90deg, #f0f8ff, #e6f3ff);
        padding: 12px;
        border-radius: 10px;
        margin-bottom: 15px;
        border-left: 5px solid #007bff;
    }
    
    .problem-header h2 {
        font-size: 1.2rem;
        margin: 0 0 8px 0;
        line-height: 1.3;
    }
    
    .status-badge {
        display: inline-block;
        padding: 5px 15px;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: bold;
        margin: 5px;
    }
    
    .status-pending {
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffeaa7;
    }
    
    .status-processing {
        background-color: #d1ecf1;
        color: #0c5460;
        border: 1px solid #bee5eb;
    }
    
    .status-resolved {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    
    .comment-card {
        background: white;
        padding: 8px 12px;
        margin-bottom: 6px;
    }
    
    .comment-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
    }
    
    .comment-author {
        font-weight: bold;
        color: #007bff;
        font-size: 0.9rem;
    }
    
    .comment-time {
        font-size: 0.75rem;
        color: #666;
    }
    
    .comment-content {
        color: #333;
        font-size: 0.9rem;
        line-height: 1.4;
        margin: 0;
    }
    
    .processing-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 8px 12px;
        margin-bottom: 6px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        border-left: 3px solid #007bff; /* Default left border for processing cards */
    }
    
    .processing-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
    }
    
    .processing-author {
        font-weight: bold;
        color: #007bff;
        font-size: 0.9rem;
    }
    
    .processing-time {
        font-size: 0.75rem;
        color: #666;
    }
    
    .processing-measure {
        color: #333;
        font-size: 0.9rem;
        line-height: 1.4;
        margin: 0;
    }
    
    /* 留言区样式 - 简化版本 */
    .comment-section {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
    }
    
    .comment-reply {
        margin-left: 20px;
        border-left: 3px solid #007bff;
        padding-left: 10px;
        background: #f0f8ff;
    }
    
    /* 处理区样式 */
    .processing-section {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
    }
    
    .processing-step {
        border-left: 4px solid #007bff;
        padding-left: 15px;
        margin-bottom: 15px;
        background: white;
        border-radius: 0 6px 6px 0;
        padding: 10px;
    }
    
    .processing-step.pending {
        border-left-color: #ffc107;
    }
    
    .processing-step.processing {
        border-left-color: #17a2b8;
    }
    
    .processing-step.completed {
        border-left-color: #28a745;
    }
    
    .processing-step.transfer {
        border-left-color: #6f42c1;
    }
    
    /* 操作按钮样式 */
    .action-button {
        margin: 5px 0;
        width: 100%;
    }
    
    .action-button-success {
        background-color: #28a745;
        border-color: #28a745;
    }
    
    .action-button-warning {
        background-color: #ffc107;
        border-color: #ffc107;
        color: #212529;
    }
    
    .action-button-info {
        background-color: #17a2b8;
        border-color: #17a2b8;
    }
</style>
""", unsafe_allow_html=True)

# 定义问题状态常量
PROBLEM_STATUS = {
    'PENDING': '待处理',
    'ASSIGNED': '已派发', 
    'PROCESSING': '处理中',
    'REPLIED': '已处理回复',
    'RESOLVED': '已办结'
}

# 定义状态流转规则
STATUS_FLOW = {
    PROBLEM_STATUS['PENDING']: [PROBLEM_STATUS['ASSIGNED'], PROBLEM_STATUS['PROCESSING']],
    PROBLEM_STATUS['ASSIGNED']: [PROBLEM_STATUS['PROCESSING'], PROBLEM_STATUS['REPLIED'], PROBLEM_STATUS['RESOLVED']],
    PROBLEM_STATUS['PROCESSING']: [PROBLEM_STATUS['REPLIED'], PROBLEM_STATUS['RESOLVED']],
    PROBLEM_STATUS['REPLIED']: [PROBLEM_STATUS['RESOLVED']],
    PROBLEM_STATUS['RESOLVED']: []  # 最终状态，无法再变更
}

def get_status_class(status):
    """获取状态对应的CSS类"""
    if PROBLEM_STATUS['PENDING'] in status:
        return 'status-pending'
    elif PROBLEM_STATUS['PROCESSING'] in status or PROBLEM_STATUS['ASSIGNED'] in status:
        return 'status-processing'
    elif PROBLEM_STATUS['RESOLVED'] in status:
        return 'status-resolved'
    else:
        return 'status-pending'

def check_user_permission(problem, action_type='view'):
    """检查用户权限 - 简化版本"""
    user_info = st.session_state.get('user_info')
    if not user_info:
        return False
    
    user_role = user_info['role']
    user_name = user_info['real_name']
    
    # 基础权限检查
    if user_role == 'admin':
        return True  # 管理员拥有所有权限
    
    # 问题创建者权限
    if problem['author'] == user_name:
        return True  # 创建者可以查看和评论
    
    # 处理人权限
    if problem.get('processing_person') == user_name:
        return True  # 处理人可以更新状态和处理记录
    
    # 特定操作权限检查
    if action_type == 'status_update':
        return user_role in ['manager', 'processor', 'admin']
    elif action_type == 'add_record':
        return user_role in ['processor', 'manager', 'admin']
    elif action_type == 'comment':
        return True  # 所有人都可以评论
    
    return False

def can_update_status(current_status, new_status):
    """检查状态是否可以更新"""
    allowed_statuses = STATUS_FLOW.get(current_status, [])
    return new_status in allowed_statuses

def update_problem_status(problem_id, new_status, operator, comment=None):
    """更新问题状态 - 增强版本"""
    # 获取当前问题信息
    problem = db.get_problem_by_id(problem_id)
    if not problem:
        st.error("问题不存在")
        return False
    
    current_status = problem['status']
    
    # 检查状态流转是否合法
    if not can_update_status(current_status, new_status):
        st.error(f"状态流转不合法：{current_status} -> {new_status}")
        return False
    
    # 检查用户权限
    if not check_user_permission(problem, 'status_update'):
        st.error("您没有权限更新问题状态")
        return False
    
    # 执行状态更新
    success = db.update_problem_status(problem_id, new_status, operator, comment)
    if success:
        st.success(f"状态已更新：{current_status} -> {new_status}")
        st.rerun()
    else:
        st.error("状态更新失败")
    
    return success

def render_problem_details(problem):
    """渲染问题详情区域 - 重新组织布局"""
    st.markdown("### 问题详情")
    
    # 第一行：发帖人和发布时间
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown(f"**发帖人：** {problem['author']}")
    with col2:
        st.markdown(f"**发布时间：** {problem['created_at']}")
    
    # 第二行：当前状态和优先级
    col3, col4 = st.columns([1, 1])
    with col3:
        st.markdown(f"**当前状态：** {problem['status']}")
    with col4:
        st.markdown(f"**优先级：** {problem.get('priority', '普通')}")
    
    # 问题内容
    st.markdown("**问题描述：**")
    st.text_area("问题描述", value=problem['description'], height=200, disabled=True, key="problem_content", label_visibility="collapsed")
    
    # 显示附件文件
    problem_files = db.get_problem_files(problem['id'])
    if problem_files:
        st.markdown("**附件文件：**")
        for file_info in problem_files:
            col_file1, col_file2, col_file3 = st.columns([3, 1, 1])
            with col_file1:
                st.markdown(f"📎 **{file_info['file_name']}**")
            with col_file2:
                st.markdown(f"大小: {file_info['file_size']} bytes")
            with col_file3:
                # 根据文件类型提供不同的打开方式
                file_extension = file_info['file_name'].lower().split('.')[-1]
                if file_extension in ['jpg', 'jpeg', 'png', 'gif']:
                    # 图片文件直接显示
                    try:
                        with open(file_info['file_path'], 'rb') as f:
                            st.image(f.read(), caption=file_info['file_name'], width=200)
                    except Exception as e:
                        st.error(f"无法显示图片: {e}")
                elif file_extension in ['pdf']:
                    # PDF文件提供下载链接
                    with open(file_info['file_path'], 'rb') as f:
                        st.download_button(
                            label="📄 下载PDF",
                            data=f.read(),
                            file_name=file_info['file_name'],
                            mime="application/pdf"
                        )
                elif file_extension in ['doc', 'docx']:
                    # Word文档提供下载链接
                    with open(file_info['file_path'], 'rb') as f:
                        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if file_extension == 'docx' else "application/msword"
                        st.download_button(
                            label="📝 下载文档",
                            data=f.read(),
                            file_name=file_info['file_name'],
                            mime=mime_type
                        )
                else:
                    # 其他文件类型提供下载链接
                    with open(file_info['file_path'], 'rb') as f:
                        st.download_button(
                            label="📁 下载文件",
                            data=f.read(),
                            file_name=file_info['file_name']
                        )
    
    # 点赞/踩交互区域 - 添加emoji图标
    # 重新获取最新的问题数据以确保显示准确
    latest_problem = db.get_problem_by_id(problem['id'])
    if latest_problem:
        # 使用最新的数据更新problem变量
        problem.update(latest_problem)
    
    col5, col6, col7 = st.columns([1, 1, 6])
    
    with col5:
        if st.button(f"👍 点赞 ({problem.get('likes', 0)})", key="detail_like", use_container_width=True):
            # 改进用户ID获取逻辑
            user_id = None
            user_info = st.session_state.get('user_info', {})
            
            if user_info and 'id' in user_info:
                user_id = user_info['id']
            elif 'user_id' in st.session_state:
                user_id = st.session_state.user_id
            else:
                st.error("请先登录后再点赞")
                return
            

            success = db.add_reaction(problem['id'], user_id, 'like')
            if success:
                st.success("点赞成功！")
                # 强制刷新页面数据
                st.rerun()
            else:
                st.error("点赞失败，请重试")
    
    with col6:
        if st.button(f"👎 踩 ({problem.get('dislikes', 0)})", key="detail_dislike", use_container_width=True):
            # 改进用户ID获取逻辑
            user_id = None
            user_info = st.session_state.get('user_info', {})
            
            if user_info and 'id' in user_info:
                user_id = user_info['id']
            elif 'user_id' in st.session_state:
                user_id = st.session_state.user_id
            else:
                st.error("请先登录后再踩")
                return
            
            # 添加调试信息
            
            success = db.add_reaction(problem['id'], user_id, 'dislike')
            if success:
                st.success("踩成功！")
                # 强制刷新页面数据
                st.rerun()
            else:
                st.error("踩失败，请重试")
    
    # 显示当前用户的反应状态
    user_id = None
    user_info = st.session_state.get('user_info', {})
    
    if user_info and 'id' in user_info:
        user_id = user_info['id']
    elif 'user_id' in st.session_state:
        user_id = st.session_state.user_id
    
    if user_id:
        user_reaction = db.get_user_reaction(problem['id'], user_id)
        if user_reaction:
            if user_reaction == 'like':
                st.success("您已点赞此问题")
            elif user_reaction == 'dislike':
                st.info("您已踩此问题")
    else:
        st.info("请登录后查看您的反应状态")

def render_comments_section(problem_id):
    """渲染留言区"""
    st.subheader("💬 留言区")
    comments = db.get_comments(problem_id)
    
    if comments:
        for comment in comments:
            # 显示留言内容 - 使用列布局
            col1, col2 = st.columns([4, 1])
            
            with col1:
                st.markdown(f"""
                <div style="background: white; padding: 12px; margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="font-weight: bold; color: #007bff; font-size: 0.9rem;">👤 {comment['author']}</div>
                        <div style="font-size: 0.75rem; color: #666;">🕒 {comment['created_at']}</div>
                    </div>
                    <div style="color: #333; font-size: 0.9rem; line-height: 1.4; margin: 0;">{comment['content']}</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                # 回复按钮放在同一行
                if st.button("回复", key=f"reply_{comment['id']}", use_container_width=True):
                    st.session_state.replying_to = comment['id']
                    st.session_state.replying_to_author = comment['author']
                    st.rerun()
            
            # 显示回复（如果有）
            replies = db.get_comment_replies(comment['id'])
            if replies:
                for reply in replies:
                    # 回复也使用列布局
                    col_reply1, col_reply2 = st.columns([4, 1])
                    
                    with col_reply1:
                        st.markdown(f"""
                        <div style="margin-left: 20px; border-left: 3px solid #007bff; background: #f8f9fa; padding: 10px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <div style="font-weight: bold; color: #6f42c1; font-size: 0.85rem;">↩️ {reply['author']}</div>
                                <div style="font-size: 0.7rem; color: #666;">🕒 {reply['created_at']}</div>
                            </div>
                            <div style="color: #333; font-size: 0.85rem; line-height: 1.4; margin: 0;">{reply['content']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col_reply2:
                        # 回复的回复按钮（如果需要的话）
                        pass  # 暂时不添加回复的回复功能
            
            # 显示回复表单
            if st.session_state.get('replying_to') == comment['id']:
                with st.form(f"reply_form_{comment['id']}"):
                    # 删除前两行内容：回复信息和回复人信息
                    # st.info(f"回复 {comment['author']} 的留言")  # 删除这行
                    # st.info(f"回复人：{reply_author}")  # 删除这行
                    
                    # 使用当前登录用户信息
                    user_info = st.session_state.get('user_info', {})
                    reply_author = user_info.get('real_name', '未知用户')
                    
                    # 修改提示文本：将"请输入回复内容..."改为"{reply_author}回复 {comment['author']}"
                    reply_content = st.text_area("回复内容", placeholder=f"{reply_author}回复 {comment['author']}：", height=60)
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.form_submit_button("提交回复"):
                            if reply_content:
                                success = db.add_comment_reply(comment['id'], reply_author, reply_content)
                                if success:
                                    st.success("回复提交成功！")
                                    st.session_state.replying_to = None
                                    st.session_state.replying_to_author = None
                                    st.rerun()
                                else:
                                    st.error("回复提交失败，请重试")
                            else:
                                st.error("请输入回复内容")
                    with col2:
                        if st.form_submit_button("取消回复"):
                            st.session_state.replying_to = None
                            st.session_state.replying_to_author = None
                            st.rerun()
            
            # 去掉分隔线，让留言之间更加紧凑
            # st.divider()  # 注释掉这行
    else:
        st.info("暂无留言")
    
    # 添加留言 - 优化布局
    with st.expander("✍️ 添加留言", expanded=False):
        with st.form("comment_form"):
            comment_content = st.text_area("留言内容", placeholder="请输入您的留言...", height=80)
            
            # 将匿名选项和提交按钮放在同一行
            col1, col2 = st.columns([1, 1])
            with col1:
                is_anonymous = st.checkbox("匿名留言", value=False)
            with col2:
                submitted = st.form_submit_button("提交留言", use_container_width=True)
            
            if submitted:
                if comment_content:
                    if is_anonymous:
                        comment_author = "匿名用户"
                    else:
                        # 使用当前登录用户信息
                        user_info = st.session_state.get('user_info', {})
                        comment_author = user_info.get('real_name', '未知用户')
                    
                    success = db.add_comment(problem_id, comment_author, comment_content)
                    if success:
                        st.success("留言提交成功！")
                        st.rerun()
                    else:
                        st.error("留言提交失败，请重试")
                else:
                    st.error("请输入留言内容")

def render_processing_section(problem):
    """渲染处理区"""
    st.subheader("⚙️ 处理区")
    
    # 获取处理记录
    processing_records = db.get_processing_records(problem['id'])
    
    # 删除调试信息选择项
    # if st.checkbox("显示调试信息", key="debug_processing"):
    #     st.write(f"处理记录数量: {len(processing_records)}")
    #     if processing_records:
    #         st.write("处理记录内容:")
    #         for i, record in enumerate(processing_records):
    #             st.write(f"记录 {i+1}: 处理人={record['processor']}, 部门={record['department']}, 措施={record['measure']}, 时间={record['created_at']}")
    
    # 首先显示发布工单信息（无论是否有处理记录）
    render_initial_work_order(problem)
    
    # 如果没有处理记录，显示提示信息
    if not processing_records:
        st.info("暂无处理记录")
        return
    
    # 按时间顺序处理记录
    all_records = []
    
    # 收集特殊操作时间，用于去重
    special_operation_times = set()
    for record in processing_records:
        measure = record['measure']
        if "调度中心转派" in measure:
            special_operation_times.add(('dispatch', record['created_at']))
        if "处理完毕回复" in measure or "处理回复" in measure:
            special_operation_times.add(('reply', record['created_at']))
        if "接单开始处理" in measure or "接单" in measure:
            special_operation_times.add(('accept', record['created_at']))
        if "驳回" in measure:
            special_operation_times.add(('reject', record['created_at']))
        if "办结" in measure:
            special_operation_times.add(('close', record['created_at']))
        if "协同" in measure:
            special_operation_times.add(('collaborate', record['created_at']))
    
    # 添加处理记录
    for record in processing_records:
        all_records.append({
            'type': 'processing',
            'operator': record['processor'],
            'action': '处理措施',
            'comment': record['measure'],
            'created_at': record['created_at'],
            'department': record['department'] if 'department' in record.keys() and record['department'] else '',
            'assigned_to': record['assigned_to'] if 'assigned_to' in record.keys() and record['assigned_to'] else ''
        })
    
    # 按时间排序
    all_records.sort(key=lambda x: x['created_at'])
    
    # 添加调试信息
    # if st.checkbox("显示调试信息", key="debug_processing_filtered"):
    #     st.write(f"处理记录数量: {len(all_records)}")
    #     for i, record in enumerate(all_records):
    #         st.write(f"处理记录 {i+1}: 类型={record['type']}, 操作={record['action']}, 内容={record['comment']}")
    
    # 渲染处理流程（跳过发布工单，因为已经在上面显示了）
    for i, record in enumerate(all_records):
        if record['type'] == 'processing':
            # 处理记录
            render_processing_record(record)

def render_processing_record(record):
    """渲染处理记录"""
    measure = record['comment']  # 这里应该是measure字段
    
    # 解析不同类型的处理记录
    if "调度中心转派" in measure:
        # 调度中心转派记录
        render_dispatch_record(record, measure)
    elif "工单转派" in measure:
        # 部门转派记录
        render_reassign_record(record, measure)
    elif "处理完毕回复" in measure or "处理回复" in measure:
        # 处理完毕回复记录
        render_reply_record(record, measure)
    elif "接单开始处理" in measure or "接单" in measure:
        # 接单处理记录
        render_accept_record(record, measure)
    elif "工单被驳回" in measure or "驳回处理回复" in measure:
        # 驳回记录（包括工单被驳回和驳回处理回复）
        render_reject_record(record, measure)
    elif "协同处理" in measure:
        # 协同处理记录
        render_collaborate_record(record, measure)
    elif "工单已办结" in measure:
        # 办结记录
        render_close_record(record, measure)
    else:
        # 其他处理记录
        render_general_record(record, measure)

def render_dispatch_record(record, measure):
    """渲染调度中心转派记录"""
    import re
    
    # 处理记录格式：'调度中心转派，转派部门：市场部，处理人：sichang2，转派意见：请市场部处理'
    
    # 优先使用数据库记录中的assigned_to字段（流转至处理人）
    target_person = ''
    if 'assigned_to' in record.keys() and record['assigned_to']:
        target_person = record['assigned_to']
    else:
        # 如果数据库字段为空，尝试从measure文本中提取
        person_match = re.search(r'处理人：([^，\n\r]+)', measure)
        if not person_match:
            person_match = re.search(r'，([^，\n\r]+)，转派意见', measure)
        target_person = person_match.group(1).strip() if person_match else '未指定'
    
    # 提取转派部门 - 从measure文本中提取，因为department字段存储的是当前处理部门
    dept_match = re.search(r'转派部门：([^，\n\r]+)', measure)
    if not dept_match:
        dept_match = re.search(r'部门：([^，\n\r]+)', measure)
    target_department = dept_match.group(1).strip() if dept_match else '未指定'
    
    # 提取转派意见
    opinion_match = re.search(r'转派意见：(.*)$', measure)
    opinion = opinion_match.group(1).strip() if opinion_match else '无转派意见'
    if not opinion.strip():
        opinion = '无转派意见'
    
    # 当前处理信息（调度中心转派）
    current_department = record['department'] if 'department' in record.keys() and record['department'] else '调度中心'
    current_person = record['operator']
    
    st.markdown(f"""
    <div class="processing-step transfer">
        <div style="font-weight: bold; color: #6f42c1; margin-bottom: 8px;">
            🔄 调度中心转派
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>转派人：</strong>{current_person} | <strong>转派时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>当前处理部门：</strong>{current_department} | <strong>当前处理人：</strong>{current_person}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>流转至部门：</strong>{target_department} | <strong>流转至处理人：</strong>{target_person}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #e2e3e5; padding: 8px; border-radius: 4px;">
            <strong>转派意见：</strong>{opinion}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_reassign_record(record, measure):
    """渲染部门转派记录"""
    import re
    
    # 提取新处理部门 - 修复正则表达式匹配实际格式
    dept_match = re.search(r'新处理部门：([^，]+)', measure)
    department = dept_match.group(1) if dept_match else (record['department'] if 'department' in record.keys() and record['department'] else '未指定')
    
    # 提取新处理人 - 修复正则表达式匹配实际格式
    person_match = re.search(r'新处理人：([^，]+)', measure)
    assigned_to = person_match.group(1) if person_match else (record['assigned_to'] if 'assigned_to' in record.keys() and record['assigned_to'] else '未指定')
    
    # 提取转派意见 - 修复正则表达式匹配实际格式
    opinion_match = re.search(r'转派意见：(.+)$', measure)
    opinion = opinion_match.group(1) if opinion_match else '无转派意见'
    
    st.markdown(f"""
    <div class="processing-step transfer">
        <div style="font-weight: bold; color: #6f42c1; margin-bottom: 8px;">
            🔄 转派信息
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>转派人：</strong>{record['operator']} | <strong>转派时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>派往部门：</strong>{department} | <strong>派往人：</strong>{assigned_to}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #e2e3e5; padding: 8px; border-radius: 4px;">
            <strong>处理意见：</strong>{opinion}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_reply_record(record, measure):
    """渲染处理完毕回复记录"""
    import re
    
    # 处理记录格式：'处理完毕回复，处理结果：具体内容'
    
    # 提取处理结果
    result_match = re.search(r'处理结果：(.+)$', measure)
    if not result_match:
        result_match = re.search(r'处理回复：(.+)$', measure)
    result = result_match.group(1).strip() if result_match else measure
    
    # 提取流转目标部门
    flow_match = re.search(r'流转至([^：]+)', measure)
    target_department = flow_match.group(1) if flow_match else '调度中心'
    
    # 当前处理信息
    current_person = record['operator']
    # 优先使用record中的department字段作为当前处理部门
    current_department = ''
    if 'department' in record.keys() and record['department']:
        current_department = record['department']
    
    if not current_department:
        # 如果department字段为空，则查询处理人的实际部门
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT department FROM users WHERE real_name = ?', (current_person,))
                user_result = cursor.fetchone()
                current_department = user_result['department'] if user_result else '未知部门'
        except:
            current_department = '未知部门'
    
    # 流转目标处理人 - 优先使用数据库记录中的assigned_to字段
    target_person = ''
    if 'assigned_to' in record.keys() and record['assigned_to']:
        target_person = record['assigned_to']
    else:
        target_person = '待分配'  # 默认值
    
    st.markdown(f"""
    <div class="processing-step processing">
        <div style="font-weight: bold; color: #17a2b8; margin-bottom: 8px;">
            ✅ 处理完成回复
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>处理人：</strong>{current_person} | <strong>处理时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>当前处理部门：</strong>{current_department} | <strong>当前处理人：</strong>{current_person}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>流转至部门：</strong>{target_department} | <strong>流转至处理人：</strong>{target_person}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #d1ecf1; padding: 8px; border-radius: 4px;">
            <strong>处理结果：</strong>{result}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_accept_record(record, measure):
    """渲染接单处理记录"""
    import re
    
    # 提取处理意见 - 修复正则表达式匹配实际格式
    opinion_match = re.search(r'处理意见：(.+)$', measure)
    opinion = opinion_match.group(1) if opinion_match else '无处理意见'
    
    # 获取当前处理部门
    current_person = record['operator']
    current_department = ''
    if 'department' in record.keys() and record['department']:
        current_department = record['department']
    
    if not current_department:
        # 如果department字段为空，则查询处理人的实际部门
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT department FROM users WHERE real_name = ?', (current_person,))
                user_result = cursor.fetchone()
                current_department = user_result['department'] if user_result else '未知部门'
        except:
            current_department = '未知部门'
    
    st.markdown(f"""
    <div class="processing-step processing">
        <div style="font-weight: bold; color: #17a2b8; margin-bottom: 8px;">
            📝 接单处理
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>处理人：</strong>{current_person} | <strong>处理时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>当前处理部门：</strong>{current_department} | <strong>当前处理人：</strong>{current_person}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #d1ecf1; padding: 8px; border-radius: 4px;">
            <strong>处理意见：</strong>{opinion}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_reject_record(record, measure):
    """渲染驳回记录"""
    import re
    
    # 判断驳回类型
    if "驳回处理回复" in measure:
        reject_type = "驳回处理回复"
        icon = "🔄"
        bg_color = "#fff3cd"
        text_color = "#856404"
    else:
        reject_type = "工单驳回"
        icon = "❌"
        bg_color = "#f8d7da"
        text_color = "#721c24"
    
    # 提取驳回原因
    reason_match = re.search(r'驳回原因：([^，]+)', measure)
    reason = reason_match.group(1) if reason_match else '无驳回原因'
    
    # 提取流转目标部门
    target_match = re.search(r'流转至([^，]+)', measure)
    target_department = target_match.group(1) if target_match else '调度中心'
    
    # 当前处理信息（驳回操作的执行部门和人员）
    current_person = record['operator']
    current_department = record['department'] if 'department' in record.keys() and record['department'] else '未知部门'
    
    # 流转至处理人
    target_person = record['assigned_to'] if 'assigned_to' in record.keys() and record['assigned_to'] else '待分配'
    
    st.markdown(f"""
    <div class="processing-step transfer">
        <div style="font-weight: bold; color: {text_color}; margin-bottom: 8px;">
            {icon} {reject_type}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>驳回人：</strong>{current_person} | <strong>驳回时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>当前处理部门：</strong>{current_department} | <strong>当前处理人：</strong>{current_person}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>流转至部门：</strong>{target_department} | <strong>流转至处理人：</strong>{target_person}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: {bg_color}; padding: 8px; border-radius: 4px;">
            <strong>驳回原因：</strong>{reason}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_general_record(record, measure):
    """渲染一般处理记录"""
    st.markdown(f"""
    <div class="processing-step transfer">
        <div style="font-weight: bold; color: #6f42c1; margin-bottom: 8px;">
            📋 处理记录
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>处理人：</strong>{record['operator']} | <strong>处理时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #e2e3e5; padding: 8px; border-radius: 4px;">
            <strong>处理内容：</strong>{measure}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_close_record(record, measure):
    """渲染办结记录"""
    import re
    
    # 提取办结意见
    opinion_match = re.search(r'办结意见：(.+)$', measure)
    opinion = opinion_match.group(1) if opinion_match else '无办结意见'
    
    # 当前处理信息（办结时的信息）
    current_person = record['operator']
    current_department = record['department'] if 'department' in record.keys() and record['department'] else '调度中心'  # 办结通常在调度中心
    
    st.markdown(f"""
    <div class="processing-step completed">
        <div style="font-weight: bold; color: #155724; margin-bottom: 8px;">
            ✅ 工单办结
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>办结人：</strong>{current_person} | <strong>办结时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>办结部门：</strong>{current_department} | <strong>办结处理人：</strong>{current_person}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>工单状态：</strong>已办结 | <strong>流程结束：</strong>无需后续处理
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #d4edda; padding: 8px; border-radius: 4px;">
            <strong>办结意见：</strong>{opinion}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_collaborate_record(record, measure):
    """渲染协同处理记录"""
    import re
    
    # 提取主要部门
    main_dept_match = re.search(r'主要部门：([^，]+)', measure)
    main_department = main_dept_match.group(1) if main_dept_match else '未指定'
    
    # 提取协同部门
    collab_dept_match = re.search(r'协同部门：([^，]+)', measure)
    collab_departments = collab_dept_match.group(1) if collab_dept_match else '未指定'
    
    # 提取协同处理人
    collab_person_match = re.search(r'协同处理人：([^，]+)', measure)
    collab_persons = collab_person_match.group(1) if collab_person_match else '未指定'
    
    # 提取协同意见
    opinion_match = re.search(r'协同意见：(.+)$', measure)
    opinion = opinion_match.group(1) if opinion_match else '无协同意见'
    
    st.markdown(f"""
    <div class="processing-step collaboration">
        <div style="font-weight: bold; color: #fd7e14; margin-bottom: 8px;">
            🤝 协同处理
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>发起人：</strong>{record['operator']} | <strong>发起时间：</strong>{record['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>主要部门：</strong>{main_department} | <strong>协同部门：</strong>{collab_departments}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>协同处理人：</strong>{collab_persons}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #fff3cd; padding: 8px; border-radius: 4px;">
            <strong>协同意见：</strong>{opinion}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_initial_work_order(problem):
    """渲染工单初始信息"""
    st.markdown(f"""
    <div class="processing-step pending">
        <div style="font-weight: bold; color: #856404; margin-bottom: 8px;">
            📋 发布工单
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>发布人：</strong>{problem['author']} | <strong>发布时间：</strong>{problem['created_at']}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>初始状态：</strong>待处理 | <strong>接收部门：</strong>{problem.get('response_department', '调度中心')}
        </div>
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
            <strong>下步处理：</strong>{problem.get('response_department', '调度中心') if problem.get('response_department', '调度中心') != '调度中心' else '等待调度中心派单'}
        </div>
        <div style="font-size: 0.9rem; color: #333; background: #fff3cd; padding: 8px; border-radius: 4px;">
            <strong>工单内容：</strong>{problem['description']}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_work_order_selection():
    """渲染工单选择界面"""
    st.markdown("### 🔍 选择要查看的工单")
    
    # 添加使用说明
    st.info("💡 **使用说明**：您可以通过以下两种方式查看工单详情：\n"
            "1. **左侧**：选择本周新建的工单\n"
            "2. **右侧**：输入工单号或编号进行搜索\n"
            "3. 查看完工单详情后，可以点击'继续查询'按钮继续查看其他工单")
    
    # 创建两列布局
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("#### 📋 本周新建工单")
        
        # 获取本周新建的工单
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取本周开始时间（周一）
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                now = datetime.now(beijing_timezone)
                days_since_monday = now.weekday()
                week_start = now - timedelta(days=days_since_monday)
                week_start_str = week_start.strftime('%Y-%m-%d')
                
                # 查询本周新建的工单
                cursor.execute('''
                    SELECT id, title, category, status, author, created_at, processing_unit
                    FROM problems 
                    WHERE DATE(created_at) >= ? 
                    ORDER BY created_at DESC
                    LIMIT 20
                ''', (week_start_str,))
                
                week_problems = cursor.fetchall()
                
                if week_problems:
                    # 创建工单选择列表
                    work_order_options = ["请选择本周工单"]
                    work_order_details = {}
                    
                    for problem in week_problems:
                        work_order_id = f"WT{str(problem[0]).zfill(5)}"
                        title = problem[1] or '无标题'
                        category = problem[2] or '未分类'
                        status = problem[3] or '待处理'
                        author = problem[4] or '未知'
                        created_at = problem[5]
                        processing_unit = problem[6] or '未分配'
                        
                        # 格式化时间
                        if created_at:
                            try:
                                if hasattr(created_at, 'strftime'):
                                    created_at_str = created_at.strftime('%m/%d %H:%M')
                                else:
                                    dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                                    created_at_str = dt.strftime('%m/%d %H:%M')
                            except:
                                created_at_str = str(created_at)
                        else:
                            created_at_str = '未知时间'
                        
                        # 构建选项文本
                        option_text = f"{work_order_id} - {title[:20]}{'...' if len(title) > 20 else ''}"
                        work_order_options.append(option_text)
                        work_order_details[option_text] = problem[0]
                    
                    # 显示工单选择
                    selected_week_work_order = st.selectbox(
                        "选择本周工单：",
                        work_order_options,
                        help="选择要查看的工单"
                    )
                    
                    if selected_week_work_order and selected_week_work_order != "请选择本周工单":
                        selected_id = work_order_details[selected_week_work_order]
                        st.session_state.selected_post_id = selected_id
                        st.rerun()
                        
                else:
                    st.info("本周暂无新建工单")
                    
        except Exception as e:
            st.error(f"获取本周工单失败: {e}")
    
    with col2:
        st.markdown("#### 🔍 工单号搜索")
        
        # 工单号搜索功能
        search_input = st.text_input(
            "输入工单号或编号：",
            placeholder="如：WT00001 或 1、10、100等",
            help="支持完整工单号或简化编号搜索"
        )
        
        if search_input:
            try:
                # 处理搜索输入
                if search_input.upper().startswith('WT'):
                    # 完整工单号格式
                    work_order_number = search_input.upper()
                    # 提取数字部分
                    try:
                        number_part = int(work_order_number[2:])
                        problem_id = number_part
                    except ValueError:
                        st.error("工单号格式错误，请检查输入")
                        return
                else:
                    # 简化编号格式
                    try:
                        problem_id = int(search_input)
                    except ValueError:
                        st.error("请输入有效的数字编号")
                        return
                
                # 验证工单是否存在
                problem = db.get_problem_by_id(problem_id)
                if problem:
                    st.success(f"找到工单：WT{str(problem_id).zfill(5)} - {problem.get('title', '无标题')}")
                    if st.button("查看该工单详情", key="view_work_order_detail"):
                        st.session_state.selected_post_id = problem_id
                        st.rerun()
                else:
                    st.error(f"未找到编号为 {problem_id} 的工单")
                    
            except Exception as e:
                st.error(f"搜索失败: {e}")
    
    # 添加返回首页按钮
    st.markdown("---")
    if st.button("返回首页", type="primary", key="return_home_selection"):
        st.switch_page("pages/主页.py")

@require_auth
def main():
    """主函数"""
    # 渲染权限控制导航侧边栏
    render_navigation_sidebar()
    
    # 初始化session_state
    if 'replying_to' not in st.session_state:
        st.session_state.replying_to = None
    if 'replying_to_author' not in st.session_state:
        st.session_state.replying_to_author = None
    
    st.markdown('<h1 style="text-align: center;">问题详情</h1>', unsafe_allow_html=True)
    
    # 获取问题ID
    problem_id = st.session_state.get('selected_post_id')
    
    if not problem_id:
        try:
            problem_id = st.query_params.get("problem_id", None)
        except:
            try:
                query_params = st.experimental_get_query_params()
                problem_id = query_params.get("problem_id", [None])[0]
            except:
                problem_id = None
    
    if not problem_id:
        render_work_order_selection()
        return
    
    try:
        problem_id = int(problem_id)
    except (ValueError, TypeError):
        st.error("问题ID格式错误")
        if st.button("返回首页", key="return_home_error_format"):
            st.switch_page("pages/主页.py")
        return
    
    # 获取问题详情
    problem = db.get_problem_by_id(problem_id)
    if not problem:
        st.error("未找到该问题")
        if st.button("返回首页", key="return_home_error_not_found"):
            st.switch_page("pages/主页.py")
        return
    
    # 记录浏览量 - 使用会话状态控制，确保每次访问只记录一次
    user_id = st.session_state.get('user_id', 'anonymous')
    
    # 检查是否已经记录过这次访问
    view_key = f"viewed_problem_{problem_id}"
    if not st.session_state.get(view_key, False):
        db.record_problem_view(problem_id, user_id)
        # 标记已记录这次访问
        st.session_state[view_key] = True
    
    # 问题头部信息
    # 格式化工单号
    work_order_id = f"WT{str(problem['id']).zfill(5)}"
    
    st.markdown(f"""
    <div class="problem-header">
        <h2>{problem['title']}</h2>
        <div>
            <span class="status-badge {get_status_class(problem['status'])}">{problem['status']}</span>
            <span style="color: #666; margin-left: 10px;">工单号: {work_order_id}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 主要内容区域 - 重新组织布局
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 问题详情区域 - 包含状态和优先级信息
        # 在渲染问题详情前，先获取最新的问题数据
        latest_problem = db.get_problem_by_id(problem_id)
        if latest_problem:
            # 使用最新的数据更新problem变量
            problem.update(latest_problem)
        
        render_problem_details(problem)
        
        # 评论区域
        render_comments_section(problem_id)
        
        # 处理记录区域
        render_processing_section(problem)
    
    with col2:
        # 右侧区域 - 统计信息和操作
        st.subheader("统计信息")
        
        # 重新获取最新的问题数据以确保统计信息准确
        latest_problem = db.get_problem_by_id(problem_id)
        if latest_problem:
            # 使用最新的数据更新problem变量
            problem.update(latest_problem)
        
        # 将统计信息整合为2行显示
        # 第一行：评论数和处理记录数
        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("评论数", len(db.get_comments(problem_id)))
        with col_stat2:
            st.metric("处理记录数", len(db.get_processing_records(problem_id)))
        
        # 第二行：浏览量、点赞数和踩数
        col_stat3, col_stat4, col_stat5 = st.columns(3)
        with col_stat3:
            # 使用真实浏览量数据
            views_count = problem.get('views', 0)
            st.metric("浏览量", views_count)
        with col_stat4:
            # 使用最新的点赞数据
            likes_count = problem.get('likes', 0)
            st.metric("点赞数", likes_count)
        with col_stat5:
            # 使用最新的踩数据
            dislikes_count = problem.get('dislikes', 0)
            st.metric("踩数", dislikes_count)
        
        # 操作区域 - 完善权限控制
        st.subheader("操作")
        
        # 添加继续查询按钮
        if st.button("🔍 继续查询其他工单", key="continue_query_right", type="primary", use_container_width=True):
            # 清除当前选中的工单ID，回到工单选择界面
            if 'selected_post_id' in st.session_state:
                del st.session_state.selected_post_id
            st.rerun()
        
        # 检查用户权限
        has_permission = check_user_permission(problem, 'status_update')
        
        if has_permission:
            # 通用操作
            st.markdown("**其他操作**")
            
            # 移除添加处理记录按钮，因为相关调度流程已在其他页面实施
            # 添加处理记录功能已移至工单调度页面，避免重复处理
            
            # 导出PDF功能
            if st.button("📄 导出PDF报告", key="export_pdf", use_container_width=True):
                with st.spinner("正在生成PDF报告..."):
                    file_path = export_manager.export_problem_detail_to_pdf(problem_id)
                    if file_path:
                        st.success("PDF报告生成成功！")
                        # 生成下载链接
                        download_link = export_manager.get_download_link(file_path, "📥 点击下载PDF报告")
                        st.markdown(download_link, unsafe_allow_html=True)
                    else:
                        st.error("PDF报告生成失败，请重试")
        
        else:
            # 无权限用户显示提示
            st.info("您暂无操作权限")
            st.markdown("如需操作，请联系管理员")
        
        # 显示当前用户信息（调试用）
        # if st.checkbox("显示调试信息", key="debug_info"):
        #     st.write("当前用户角色:", st.session_state.get('user_role', 'user'))
        #     st.write("当前用户名称:", st.session_state.get('user_name', '未登录'))
        #     st.write("问题创建者:", problem['author'])
        #     st.write("处理人:", problem.get('processing_person', '未分配'))
        #     st.write("当前状态:", problem['status'])
    
    # 页面底部操作按钮
    st.markdown("---")
    st.markdown("### 其他操作")
    
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
    
    with col_btn1:
        if st.button("📋 返回工单列表", key="return_to_list", use_container_width=True):
            st.switch_page("pages/主页.py")
    
    with col_btn2:
        if st.button("🏠 返回首页", key="return_to_home", use_container_width=True):
            st.switch_page("pages/主页.py")
    
    with col_btn3:
        if st.button("🔄 刷新页面", key="refresh_page", use_container_width=True):
            st.rerun()

if __name__ == "__main__":
    main() 