import streamlit as st
from auth_manager import auth_manager
from verification_manager import VerificationManager
import sqlite3

# 页面配置
st.set_page_config(
    page_title="用户注册",
    page_icon="📝",
    layout="centered"
)

def main():
    """主函数"""
    st.markdown('<h1 style="text-align: center;">📝 用户注册</h1>', unsafe_allow_html=True)
    
    # 初始化验证码管理器
    verification_mgr = VerificationManager()
    
    # 第一步：验证码验证（在表单外部）
    st.markdown("### 🔐 第一步：验证身份")
    
    # 使用列布局来放置验证码输入框和验证按钮
    col1, col2 = st.columns([3, 1])
    
    with col1:
        verification_code = st.text_input(
            "注册验证码 *", 
            placeholder="请输入8位数字验证码（工号牌后4位+手机尾号后4位）",
            max_chars=8,
            help="验证码格式：工号牌后4位+手机尾号后4位，例如：12345678",
            key="verification_code_input"
        )
    
    with col2:
        # 添加验证按钮
        if st.button("🔍 验证", type="secondary", use_container_width=True):
            # 验证按钮被点击时的验证逻辑
            if verification_code:
                if len(verification_code) != 8 or not verification_code.isdigit():
                    st.warning("⚠️ 验证码必须是8位数字")
                    st.session_state['verification_info'] = None
                else:
                    code_info = verification_mgr.verify_code(verification_code)
                    if code_info:
                        if code_info['used_by']:
                            st.error("❌ 此验证码已被使用")
                            st.session_state['verification_info'] = None
                        else:
                            st.success(f"✅ 验证码有效 - 工号尾号：{code_info['employee_id_suffix']}，手机尾号：{code_info['phone_suffix']}")
                            # 将验证码信息存储到session state
                            st.session_state['verification_info'] = code_info
                            st.rerun()
                    else:
                        st.error("❌ 验证码无效或已过期")
                        st.session_state['verification_info'] = None
            else:
                st.warning("⚠️ 请输入验证码")
    
    # 实时验证显示（当输入框内容变化时）
    if verification_code:
        if len(verification_code) != 8 or not verification_code.isdigit():
            st.warning("⚠️ 验证码必须是8位数字")
            st.session_state['verification_info'] = None
        else:
            # 检查是否已经有验证信息
            if 'verification_info' not in st.session_state or st.session_state['verification_info'] is None:
                # 自动验证验证码
                code_info = verification_mgr.verify_code(verification_code)
                if code_info:
                    if code_info['used_by']:
                        st.error("❌ 此验证码已被使用")
                        st.session_state['verification_info'] = None
                    else:
                        st.success(f"✅ 验证码有效 - 工号尾号：{code_info['employee_id_suffix']}，手机尾号：{code_info['phone_suffix']}")
                        # 将验证码信息存储到session state
                        st.session_state['verification_info'] = code_info
                        st.rerun()
                else:
                    st.error("❌ 验证码无效或已过期")
                    st.session_state['verification_info'] = None
    
    st.markdown("---")
    st.markdown("### 📝 第二步：填写注册信息")
    
    # 只有验证码验证通过才显示注册表单
    if 'verification_info' in st.session_state and st.session_state['verification_info'] is not None:
        # 注册表单
        with st.form("register_form"):
            username = st.text_input("用户名 *", placeholder="请输入用户名")
            password = st.text_input("密码 *", placeholder="请输入密码", type="password")
            confirm_password = st.text_input("确认密码 *", placeholder="请再次输入密码", type="password")
            
            real_name = st.text_input("真实姓名 *", placeholder="请输入真实姓名")
            email = st.text_input("邮箱", placeholder="请输入邮箱地址")
            phone = st.text_input("手机号 *", placeholder="请输入手机号")
            
            # 部门选择（下拉选项）
            departments = [
                "市场部", "集客部", "网络部", "全业务支撑中心", "客体部", 
                "综合部", "党建部", "人力部", "财务部", "工会",
                "纪委办", "船山", "射洪", "蓬溪",  "大英","安居"
            ]
            department = st.selectbox("部门", departments, index=None, placeholder="请选择部门")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                submitted = st.form_submit_button("📝 注册", type="primary", use_container_width=True)
            with col2:
                if st.form_submit_button("🔙 返回登录", use_container_width=True):
                    st.switch_page("pages/登录.py")
            
            if submitted:
                # 验证输入
                if not username or not password or not confirm_password or not real_name or not phone:
                    st.error("❌ 请填写必填项")
                    return
                
                if password != confirm_password:
                    st.error("❌ 两次输入的密码不一致")
                    return
                
                if len(password) < 6:
                    st.error("❌ 密码长度至少6位")
                    return
                
                # 验证手机号尾号是否与验证码匹配
                phone_suffix = phone[-4:] if len(phone) >= 4 else ""
                if phone_suffix != st.session_state['verification_info']['phone_suffix']:
                    st.error("❌ 手机号尾号与验证码不匹配")
                    return
                
                # 检查用户名是否已存在
                try:
                    with sqlite3.connect('feedback.db') as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
                        if cursor.fetchone():
                            st.error("❌ 用户名已存在，请选择其他用户名")
                            return
                except Exception as e:
                    st.error(f"❌ 检查用户名失败: {e}")
                    return
                
                # 创建用户
                user_data = {
                    'username': username,
                    'password': password,
                    'real_name': real_name,
                    'email': email,
                    'phone': phone,
                    'department': department if department else None,
                    'role': 'user'
                }
                
                created_by = st.session_state.get('user_id', None)
                success = auth_manager.create_user(user_data, created_by)
                
                if success:
                    # 标记验证码为已使用
                    verification_mgr.mark_code_as_used(
                        st.session_state['verification_info']['id'], 
                        username
                    )
                    
                    st.success("✅ 注册成功！请登录")
                    # 清除验证信息
                    if 'verification_info' in st.session_state:
                        del st.session_state['verification_info']
                    
                    # 延迟跳转
                    import time
                    time.sleep(2)
                    st.switch_page("pages/登录.py")
                else:
                    st.error("❌ 注册失败，请检查输入信息或联系管理员")
                    
                    # 添加详细错误信息用于调试
                    if st.checkbox("🔧 显示详细错误信息", key="show_register_error_details"):
                        st.write("**调试信息：**")
                        st.write(f"- 用户名: {username}")
                        st.write(f"- 真实姓名: {real_name}")
                        st.write(f"- 角色: {user_data['role']}")
                        st.write(f"- 部门: {department if department else '未选择'}")
                        st.write(f"- 创建者ID: {created_by}")
                        st.write(f"- 当前登录状态: {'已登录' if 'user_info' in st.session_state else '未登录'}")
                        
                        # 检查用户名是否已存在
                        try:
                            with sqlite3.connect('feedback.db') as conn:
                                cursor = conn.cursor()
                                cursor.execute('SELECT id, username, role, status FROM users WHERE username = ?', (username,))
                                existing_user = cursor.fetchone()
                                if existing_user:
                                    st.error(f"❌ 用户名 '{username}' 已存在 (ID: {existing_user[0]}, 角色: {existing_user[2]}, 状态: {existing_user[3]})")
                                else:
                                    st.success(f"✅ 用户名 '{username}' 可用")
                        except Exception as e:
                            st.error(f"❌ 检查用户名时出错: {e}")
                        
                        # 检查数据库连接和表结构
                        try:
                            with sqlite3.connect('feedback.db') as conn:
                                cursor = conn.cursor()
                                cursor.execute("PRAGMA table_info(users)")
                                columns = cursor.fetchall()
                                st.write("**用户表结构：**")
                                for col in columns:
                                    st.write(f"- {col[1]} ({col[2]})")
                        except Exception as e:
                            st.error(f"❌ 检查数据库结构时出错: {e}")
    else:
        st.info("ℹ️ 请先输入有效的注册验证码")
        
        # 添加一个提示框说明如何获取验证码
        with st.expander("💡 如何获取验证码？", expanded=False):
            st.markdown("""
            **验证码获取方式：**
            
            1. **联系管理员**：向系统管理员申请注册验证码
            2. **验证码格式**：8位数字，由工号牌后4位+手机尾号后4位组成
            3. **示例说明**：
               - 工号牌后4位：1234
               - 手机尾号后4位：5678
               - 验证码：12345678
            
            **注意**：每个验证码只能使用一次，使用后自动失效。
            """)

if __name__ == "__main__":
    main() 