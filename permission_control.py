#!/usr/bin/env python3
"""
权限控制模块
实现基于角色的访问控制（RBAC）
"""

import streamlit as st
from functools import wraps
from auth_manager import auth_manager

# 定义角色权限映射
ROLE_PERMISSIONS = {
    'user': {
        'pages': ['登录', '个人信息修改', '主页', '问题详情'],
        'description': '普通用户：可以查看问题、提交反馈、修改个人信息'
    },
    'processor': {
        'pages': ['登录', '个人信息修改', '主页', '问题详情', '工单调度'],
        'description': '处理员：可以处理工单、更新状态、添加处理记录'
    },
    'manager': {
        'pages': ['登录', '个人信息修改', '主页', '问题详情', '工单调度'],
        'description': '经理：可以分配工单、导出数据、查看用户信息'
    },
    'admin': {
        'pages': ['登录', '个人信息修改', '主页', '问题详情', '工单调度', '用户管理'],
        'description': '系统管理员：可以管理用户、系统配置、删除问题'
    }
}

def require_auth(func):
    """要求用户已登录的装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not auth_manager.check_session():
            st.warning("⚠️ 请先登录才能访问此页面")
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🔐 前往登录", key="go_to_login", type="primary", use_container_width=True):
                    st.switch_page("pages/登录.py")
            with col2:
                if st.button("🏠 返回首页", key="go_to_main", use_container_width=True):
                    st.switch_page("main.py")
            return
        return func(*args, **kwargs)
    return wrapper

def require_role(allowed_roles):
    """要求特定角色的装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not auth_manager.check_session():
                st.warning("⚠️ 请先登录才能访问此页面")
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("🔐 前往登录", key="go_to_login", type="primary", use_container_width=True):
                        st.switch_page("pages/登录.py")
                with col2:
                    if st.button("🏠 返回首页", key="go_to_main", use_container_width=True):
                        st.switch_page("main.py")
                return
            
            user_info = st.session_state.get('user_info', {})
            user_role = user_info.get('role', 'user')
            
            if user_role not in allowed_roles:
                st.error(f"❌ 权限不足！")
                st.info(f"您的角色是：**{user_role}**\n\n此页面需要以下角色之一：**{', '.join(allowed_roles)}**")
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("🏠 返回主页", key="return_to_home", type="primary", use_container_width=True):
                        st.switch_page("pages/主页.py")
                with col2:
                    if st.button("📋 查看权限", key="view_permissions", use_container_width=True):
                        show_role_permissions(user_role)
                return
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def require_permission(required_permission):
    """要求特定权限的装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not auth_manager.check_session():
                st.warning("⚠️ 请先登录才能访问此页面")
                if st.button("🔐 前往登录", key="go_to_login", type="primary"):
                    st.switch_page("pages/登录.py")
                return
            
            user_info = st.session_state.get('user_info', {})
            user_role = user_info.get('role', 'user')
            
            if not auth_manager.check_permission(user_role, required_permission):
                st.error(f"❌ 权限不足！您没有执行此操作的权限。")
                if st.button("🏠 返回主页", key="return_to_home", type="primary"):
                    st.switch_page("pages/主页.py")
                return
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def get_user_role():
    """获取当前用户角色"""
    if not auth_manager.check_session():
        return None
    
    user_info = st.session_state.get('user_info', {})
    return user_info.get('role', 'user')

def get_user_permissions():
    """获取当前用户权限"""
    user_role = get_user_role()
    if not user_role:
        return []
    
    return ROLE_PERMISSIONS.get(user_role, {}).get('pages', [])

def can_access_page(page_name):
    """检查用户是否可以访问指定页面"""
    user_permissions = get_user_permissions()
    return page_name in user_permissions

def show_role_permissions(user_role):
    """显示角色权限信息"""
    role_info = ROLE_PERMISSIONS.get(user_role, {})
    st.markdown(f"### 👤 您的角色：{user_role}")
    st.info(role_info.get('description', '无角色说明'))
    
    st.markdown("### 📋 可访问页面：")
    pages = role_info.get('pages', [])
    for page in pages:
        st.markdown(f"- ✅ {page}")

def render_navigation_sidebar():
    """渲染基于权限的导航侧边栏"""
    if not auth_manager.check_session():
        st.sidebar.warning("请先登录")
        if st.sidebar.button("🔐 用户登录", key="sidebar_login", use_container_width=True):
            st.switch_page("pages/登录.py")
        if st.sidebar.button("📝 用户注册", key="sidebar_register", use_container_width=True):
            st.switch_page("pages/注册.py")
        return
    
    # 获取用户信息
    user_info = st.session_state.get('user_info', {})
    user_role = user_info.get('role', 'user')
    real_name = user_info.get('real_name', '未知用户')
    
    # 显示用户信息
    st.sidebar.markdown(f"**👤 当前用户：** {real_name}")
    st.sidebar.markdown(f"**🔑 角色：** {user_role}")
    st.sidebar.markdown(f"**🏢 部门：** {user_info.get('department', '未设置')}")
    
    st.sidebar.divider()
    
    # 根据角色显示可访问的页面
    role_info = ROLE_PERMISSIONS.get(user_role, {})
    
    st.sidebar.markdown("**🧭 导航菜单**")
    
    # 主页（所有用户都可以访问）
    if st.sidebar.button("🏠 主页", key="nav_home", use_container_width=True):
        st.switch_page("pages/主页.py")
    
    # 个人信息修改（所有用户都可以访问）
    if st.sidebar.button("👤 个人信息修改", key="nav_profile", use_container_width=True):
        st.switch_page("pages/个人信息修改.py")
    
    # 问题详情（所有用户都可以访问）
    if st.sidebar.button("📋 问题详情", key="nav_problem_detail", use_container_width=True):
        st.switch_page("pages/问题详情.py")
    
    # 工单调度（processor及以上角色）
    if user_role in ['processor', 'manager', 'admin']:
        if st.sidebar.button("📋 工单调度", key="nav_work_order", use_container_width=True):
            st.switch_page("pages/工单调度.py")
    
    # 用户管理（仅admin）
    if user_role == 'admin':
        if st.sidebar.button("👥 用户管理", key="nav_user_management", use_container_width=True):
            st.switch_page("pages/用户管理.py")
    
    st.sidebar.divider()
    
    # 角色说明
    st.sidebar.markdown("**ℹ️ 角色说明**")
    st.sidebar.info(role_info.get('description', '无角色说明'))
    
    # 退出登录
    if st.sidebar.button("🚪 退出登录", key="logout", type="secondary", use_container_width=True):
        if 'session_token' in st.session_state:
            auth_manager.logout(st.session_state.session_token)
        st.session_state.clear()
        st.rerun()

def render_unauthorized_page():
    """渲染未授权页面"""
    st.error("❌ 未登录或权限不足")
    st.markdown("### 请选择以下操作：")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("🔐 用户登录", key="login_unauth", type="primary", use_container_width=True):
            st.switch_page("pages/登录.py")
    
    with col2:
        if st.button("📝 用户注册", key="register_unauth", use_container_width=True):
            st.switch_page("pages/注册.py")
    
    with col3:
        if st.button("🏠 返回首页", key="home_unauth", use_container_width=True):
            st.switch_page("main.py")
