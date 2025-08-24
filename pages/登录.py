import streamlit as st
from auth_manager import auth_manager
import sqlite3

# 页面配置
st.set_page_config(
    page_title="用户登录",
    page_icon="🔐",
    layout="centered"
)

def main():
    """主函数"""
    st.markdown('<h1 style="text-align: center;">一线之声</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666; font-size: 1.2rem;">🔐 用户登录系统</p>', unsafe_allow_html=True)

    
    # 如果已经登录，显示用户信息和退出选项
    if 'user_info' in st.session_state and st.session_state.user_info:
        user_info = st.session_state.user_info
        st.success(f"✅ 您已登录 - {user_info['real_name']} ({user_info['role']})")
        
        # 显示用户详细信息
        with st.expander("👤 用户信息", expanded=False):
            st.write(f"**用户名：** {user_info['username']}")
            st.write(f"**真实姓名：** {user_info['real_name']}")
            st.write(f"**角色：** {user_info['role']}")
            if user_info.get('email'):
                st.write(f"**邮箱：** {user_info['email']}")
            if user_info.get('department'):
                st.write(f"**部门：** {user_info['department']}")
        
        # 操作按钮
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("🏠 前往主页", use_container_width=True):
                st.switch_page("pages/主页.py")
        with col2:
            if st.button("✏️ 个人信息修改", use_container_width=True):
                st.switch_page("pages/个人信息修改.py")
        with col3:
            if st.button("🚪 退出登录", type="secondary", use_container_width=True):
                # 执行退出登录
                if 'session_token' in st.session_state:
                    auth_manager.logout(st.session_state.session_token)
                # 清除所有会话状态
                st.session_state.clear()
                st.success("✅ 已成功退出登录")
                st.rerun()
        
        return
    
    # 登录表单
    with st.form("login_form"):
        username = st.text_input("用户名", placeholder="请输入用户名")
        password = st.text_input("密码", placeholder="请输入密码", type="password")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            submitted = st.form_submit_button("🔐 登录", type="primary", use_container_width=True)
        with col2:
            if st.form_submit_button("📝 注册", use_container_width=True):
                st.switch_page("pages/注册.py")
        
        if submitted:
            if not username or not password:
                st.error("❌ 请输入用户名和密码")
                return
            
            # 验证用户
            user_info = auth_manager.authenticate_user(username, password)
            if user_info:
                # 创建会话
                session_token = auth_manager.create_session(user_info['id'])
                if session_token:
                    # 保存用户信息到session_state
                    st.session_state.user_info = user_info
                    st.session_state.session_token = session_token
                    st.session_state.user_id = user_info['id']
                    st.session_state.user_name = user_info['real_name']
                    st.session_state.user_role = user_info['role']
                    
                    st.success(f"🎉 欢迎回来，{user_info['real_name']}！")
                    st.rerun()
                else:
                    st.error("❌ 创建会话失败，请重试")
            else:
                st.error("❌ 用户名或密码错误")
                
                # 添加详细错误信息
                if st.checkbox("显示详细错误信息", key="show_error_details"):
                    try:
                        with sqlite3.connect('feedback.db') as conn:
                            cursor = conn.cursor()
                            cursor.execute('SELECT username, status FROM users WHERE username = ?', (username,))
                            user = cursor.fetchone()
                            if user:
                                st.write(f"用户存在，状态: {user[1]}")
                                if user[1] != 'active':
                                    st.error(f"用户状态为 {user[1]}，无法登录")
                            else:
                                st.write("用户不存在")
                    except Exception as e:
                        st.write(f"检查用户时出错: {e}")
    
    # 显示测试账户信息
    with st.expander("📋 测试账户信息", expanded=False):
        st.markdown("""
        ### 默认测试账户
        
        | 角色 | 用户名 | 密码 | 权限说明 |
        |------|--------|------|----------|
        | 系统管理员 | admin | admin123 | 所有权限 |
        | 经理 | manager | manager123 | 处理人权限 + 分配问题、导出数据、查看用户 |
        | 处理人 | processor | processor123 | 普通用户权限 + 处理问题、更新状态、添加处理记录 |
        | 普通用户 | user | user123 | 查看问题、创建问题、评论、点赞 |
        
        ### 权限级别说明
        
        - **普通用户(user)**：查看问题、创建问题、评论、点赞
        - **处理人(processor)**：普通用户权限 + 处理问题、更新状态、添加处理记录
        - **经理(manager)**：处理人权限 + 分配问题、导出数据、查看用户
        - **系统管理员(admin)**：所有权限 + 用户管理、系统配置
        """)
    
    # 返回主页
    if st.button("🏠 返回主页"):
        st.switch_page("pages/主页.py")
    
    # 添加备案信息
    st.markdown("---")
    st.markdown(
        '<div style="text-align: center; color: #666; font-size: 0.8rem; padding: 10px;">'
        '蜀ICP备2025155786号 | sndqt.cn @旦求誊 版权所有'
        '</div>',
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main() 