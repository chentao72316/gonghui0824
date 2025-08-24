import streamlit as st
import logging
from auth_manager import auth_manager

# 设置日志级别，减少文件监控日志
logging.getLogger('streamlit').setLevel(logging.ERROR)
logging.getLogger('streamlit.runtime').setLevel(logging.ERROR)
logging.getLogger('streamlit.runtime.scriptrunner').setLevel(logging.ERROR)

# 页面配置
st.set_page_config(
    page_title="一线心声 - 欢迎",
    page_icon="📋",
    layout="centered"
)

def main():
    """启动页面主函数"""
    
    # 检查用户是否已登录
    if auth_manager.check_session():
        # 已登录，直接跳转到主页
        st.switch_page("pages/主页.py")
        return
    
    # 未登录，显示欢迎页面和登录选项
    st.markdown('<h1 style="text-align: center;">📋 一线心声</h1>', unsafe_allow_html=True)
    st.markdown('<h3 style="text-align: center;">欢迎使用一线心声系统</h3>', unsafe_allow_html=True)
    
    # 添加系统介绍
    with st.expander("📋 系统介绍", expanded=False):
        st.markdown("""
        **一线心声** 是一个专门为一线员工设计的反馈和工单管理系统，主要功能包括：
        
        - 📝 **问题反馈**：提交工作问题和建议
        - 🔄 **工单管理**：跟踪问题处理进度
        - 👥 **多部门协作**：支持跨部门问题处理
        - 📊 **数据统计**：问题分析和趋势报告
        - 🔐 **权限管理**：基于角色的访问控制
        """)
    
    # 登录和注册按钮
    st.markdown("---")
    st.markdown("### 请选择操作")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("🔐 用户登录", type="primary", use_container_width=True, key="login_btn"):
            st.switch_page("pages/登录.py")
    
    with col2:
        if st.button("📝 用户注册", use_container_width=True, key="register_btn"):
            st.switch_page("pages/注册.py")
    
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
