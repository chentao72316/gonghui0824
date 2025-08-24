import streamlit as st
from auth_manager import auth_manager
import sqlite3
from permission_control import require_auth, render_navigation_sidebar

# 页面配置
st.set_page_config(
    page_title="个人信息修改",
    page_icon="✏️",
    layout="centered"
)

@require_auth
def main():
    """主函数"""
    # 渲染权限控制导航侧边栏
    render_navigation_sidebar()
    
    user_info = st.session_state.user_info
    st.markdown('<h1 style="text-align: center;">✏️ 个人信息修改</h1>', unsafe_allow_html=True)
    
    # 显示当前用户信息
    st.info(f"当前用户：{user_info['username']} ({user_info['real_name']})")
    
    # 预定义部门列表
    departments = [
        "市场部", "集客部", "网络部", "全业务支撑中心", "客体部", 
        "综合部", "党群部", "人力部", "财务部", "工会", 
        "纪委办", "船山", "射洪", "蓬溪", "安居"
    ]
    
    # 个人信息修改表单
    with st.form("profile_edit_form"):
        # 用户名（只读显示）
        st.text_input("用户名", value=user_info['username'], disabled=True, help="用户名不可修改")
        
        # 密码修改
        st.subheader("🔐 密码修改")
        current_password = st.text_input("当前密码", type="password", placeholder="请输入当前密码")
        new_password = st.text_input("新密码", type="password", placeholder="请输入新密码")
        confirm_new_password = st.text_input("确认新密码", type="password", placeholder="请再次输入新密码")
        
        st.divider()
        
        # 基本信息修改
        st.subheader("👤 基本信息修改")
        real_name = st.text_input("真实姓名 *", value=user_info.get('real_name', ''), placeholder="请输入真实姓名")
        email = st.text_input("邮箱", value=user_info.get('email', ''), placeholder="请输入邮箱地址")
        phone = st.text_input("手机号", value=user_info.get('phone', ''), placeholder="请输入手机号")
        
        # 部门选择
        current_dept_index = None
        if user_info.get('department') in departments:
            current_dept_index = departments.index(user_info.get('department'))
        department = st.selectbox("部门", departments, index=current_dept_index, 
                                placeholder="请选择部门")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            submitted = st.form_submit_button("💾 保存修改", type="primary", use_container_width=True)
        with col2:
            if st.form_submit_button("🔙 返回", use_container_width=True):
                st.switch_page("pages/主页.py")
        
        if submitted:
            # 验证输入
            if not real_name:
                st.error("❌ 真实姓名为必填项")
                return
            
            # 如果修改密码，验证密码
            if new_password or confirm_new_password:
                if not current_password:
                    st.error("❌ 修改密码时必须输入当前密码")
                    return
                
                if not new_password:
                    st.error("❌ 请输入新密码")
                    return
                
                if not confirm_new_password:
                    st.error("❌ 请确认新密码")
                    return
                
                if new_password != confirm_new_password:
                    st.error("❌ 两次输入的新密码不一致")
                    return
                
                if len(new_password) < 6:
                    st.error("❌ 新密码长度至少6位")
                    return
            
            # 准备更新数据
            update_data = {
                'real_name': real_name,
                'email': email,
                'phone': phone,
                'department': department
            }
            
            # 如果修改了密码，添加密码更新
            if new_password:
                update_data['password'] = new_password
            
            # 更新用户信息
            success = auth_manager.update_user_profile(user_info['id'], update_data)
            
            if success:
                st.success("✅ 个人信息修改成功")
                st.rerun()
            else:
                st.error("❌ 个人信息修改失败")
    
    # 返回主页
    if st.button("🏠 返回主页"):
        st.switch_page("pages/主页.py")

if __name__ == "__main__":
    main() 