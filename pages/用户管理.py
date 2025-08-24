import streamlit as st
import pandas as pd
from auth_manager import auth_manager
from permission_control import require_role, render_navigation_sidebar

# 页面配置
st.set_page_config(
    page_title="用户管理",
    page_icon="👥",
    layout="wide"
)

def check_admin_permission():
    """检查管理员权限"""
    user_role = st.session_state.get('user_role')
    if user_role != 'admin':
        st.error("❌ 您没有权限访问此页面")
        st.stop()

@require_role(['admin'])
def main():
    """主函数"""
    # 渲染权限控制导航侧边栏
    render_navigation_sidebar()
    
    st.markdown('<h1 style="text-align: center;">👥 用户管理</h1>', unsafe_allow_html=True)
    
    # 预定义部门列表
    departments = [
        "调度中心","市场部", "集客部", "网络部", "全业务支撑中心", "客体部", 
        "综合部", "党建部", "人力部", "财务部", "工会",
        "纪委办", "船山", "射洪", "蓬溪","大英", "安居"
    ]
    
    # 获取所有用户
    users = auth_manager.get_all_users()
    
    # 统计信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("👥 总用户数", len(users))
    with col2:
        active_users = len([u for u in users if u['status'] == 'active'])
        st.metric("✅ 活跃用户", active_users)
    with col3:
        admin_users = len([u for u in users if u['role'] == 'admin'])
        st.metric("👑 管理员", admin_users)
    with col4:
        manager_users = len([u for u in users if u['role'] == 'manager'])
        st.metric("👨‍ 经理", manager_users)
    
    st.divider()
    
    # 用户列表
    st.subheader("📋 用户列表")
    
    if users:
        # 转换为DataFrame
        df = pd.DataFrame(users)
        df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        df['last_login'] = pd.to_datetime(df['last_login']).dt.strftime('%Y-%m-%d %H:%M')
        
        # 显示用户表格
        st.dataframe(
            df[['username', 'real_name', 'email', 'department', 'role', 'status', 'created_at', 'last_login']],
            use_container_width=True
        )
        
        # 用户操作
        st.subheader("⚙️ 用户操作")
        
        # 添加新用户
        with st.expander("➕ 添加新用户", expanded=False):
            with st.form("add_user_form"):
                new_username = st.text_input("用户名 *", key="new_username")
                new_password = st.text_input("密码 *", type="password", key="new_password")
                new_real_name = st.text_input("真实姓名 *", key="new_real_name")
                new_email = st.text_input("邮箱", key="new_email")
                new_department = st.selectbox("部门", departments, index=None, placeholder="请选择部门", key="new_department")
                new_role = st.selectbox("角色 *", ["user", "processor", "manager", "admin"], key="new_role")
                
                if st.form_submit_button("➕ 添加用户"):
                    if new_username and new_password and new_real_name:
                        user_data = {
                            'username': new_username,
                            'password': new_password,
                            'real_name': new_real_name,
                            'email': new_email,
                            'department': new_department,
                            'role': new_role
                        }
                        
                        created_by = st.session_state.get('user_id')
                        success = auth_manager.create_user(user_data, created_by)
                        
                        if success:
                            st.success("✅ 用户添加成功")
                            st.rerun()
                        else:
                            st.error("❌ 用户添加失败")
                    else:
                        st.error("❌ 请填写必填项")
        
        # 编辑用户
        with st.expander("✏️ 编辑用户", expanded=False):
            user_options = {f"{u['username']} ({u['real_name']})": u['id'] for u in users}
            selected_user = st.selectbox("选择用户", list(user_options.keys()))
            
            if selected_user:
                user_id = user_options[selected_user]
                user = next((u for u in users if u['id'] == user_id), None)
                
                if user:
                    with st.form("edit_user_form"):
                        edit_real_name = st.text_input("真实姓名 *", value=user['real_name'], key="edit_real_name")
                        edit_email = st.text_input("邮箱", value=user['email'] or "", key="edit_email")
                        
                        # 部门下拉选择
                        current_dept_index = None
                        if user['department'] in departments:
                            current_dept_index = departments.index(user['department'])
                        edit_department = st.selectbox("部门", departments, index=current_dept_index, 
                                                     placeholder="请选择部门", key="edit_department")
                        
                        edit_role = st.selectbox("角色 *", ["user", "processor", "manager", "admin"], 
                                               index=["user", "processor", "manager", "admin"].index(user['role']),
                                               key="edit_role")
                        edit_status = st.selectbox("状态 *", ["active", "inactive", "suspended"],
                                                 index=["active", "inactive", "suspended"].index(user['status']),
                                                 key="edit_status")
                        
                        if st.form_submit_button("💾 更新用户"):
                            if edit_real_name:
                                user_data = {
                                    'real_name': edit_real_name,
                                    'email': edit_email,
                                    'department': edit_department,
                                    'role': edit_role,
                                    'status': edit_status
                                }
                                
                                success = auth_manager.update_user(user_id, user_data)
                                
                                if success:
                                    st.success("✅ 用户信息更新成功")
                                    st.rerun()
                                else:
                                    st.error("❌ 用户信息更新失败")
                            else:
                                st.error("❌ 请填写必填项")
        
        # 删除用户
        with st.expander("🗑️ 删除用户", expanded=False):
            delete_user_options = {f"{u['username']} ({u['real_name']}) - {u['role']}": u['id'] for u in users}
            user_to_delete = st.selectbox("选择要删除的用户", list(delete_user_options.keys()))
            
            if user_to_delete:
                delete_user_id = delete_user_options[user_to_delete]
                user_to_delete_info = next((u for u in users if u['id'] == delete_user_id), None)
                
                if user_to_delete_info:
                    st.warning(f"⚠️ 即将删除用户: {user_to_delete_info['username']} ({user_to_delete_info['real_name']})")
                    st.write(f"**用户信息：**")
                    st.write(f"- 用户名: {user_to_delete_info['username']}")
                    st.write(f"- 真实姓名: {user_to_delete_info['real_name']}")
                    st.write(f"- 角色: {user_to_delete_info['role']}")
                    st.write(f"- 部门: {user_to_delete_info['department'] or '未设置'}")
                    st.write(f"- 状态: {user_to_delete_info['status']}")
                    
                    # 防止删除自己
                    current_user_id = st.session_state.get('user_id')
                    if delete_user_id == current_user_id:
                        st.error("❌ 不能删除当前登录用户")
                    else:
                        if st.button("🗑️ 确认删除", type="secondary"):
                            success = auth_manager.delete_user(delete_user_id)
                            
                            if success:
                                st.success("✅ 用户删除成功")
                                st.rerun()
                            else:
                                st.error("❌ 用户删除失败")
    else:
        st.info("📭 暂无用户数据")
    
    # 返回主页
    if st.button("🏠 返回主页"):
        st.switch_page("pages/主页.py")

if __name__ == "__main__":
    main() 