import streamlit as st
from verification_manager import VerificationManager
import pandas as pd
import io
import sqlite3

# 页面配置
st.set_page_config(
    page_title="验证码管理",
    page_icon="🔐",
    layout="wide"
)

def main():
    """主函数"""
    st.markdown('<h1 style="text-align: center;">🔐 注册验证码管理</h1>', unsafe_allow_html=True)
    
    # 检查管理员权限
    if 'user_info' not in st.session_state or st.session_state['user_info']['role'] != 'admin':
        st.error("❌ 权限不足，只有管理员可以访问此页面")
        return
    
    verification_mgr = VerificationManager()
    
    # 创建两列布局
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### 📤 导入验证码")
        
        # 文件上传
        uploaded_file = st.file_uploader(
            "选择Excel文件", 
            type=['xlsx', 'xls'],
            help="Excel文件应包含：工号牌后4位、手机尾号后4位"
        )
        
        if uploaded_file is not None:
            if st.button("📥 导入验证码", type="primary"):
                if verification_mgr.import_from_excel(uploaded_file):
                    st.rerun()
        
        # 手动添加验证码
        st.markdown("### ➕ 手动添加验证码")
        with st.form("add_code_form"):
            employee_suffix = st.text_input("工号牌后4位", max_chars=4, help="例如：1234")
            phone_suffix = st.text_input("手机尾号后4位", max_chars=4, help="例如：5678")
            
            if st.form_submit_button("➕ 添加"):
                if employee_suffix and phone_suffix:
                    if len(employee_suffix) == 4 and len(phone_suffix) == 4 and employee_suffix.isdigit() and phone_suffix.isdigit():
                        if verification_mgr.add_single_code(employee_suffix, phone_suffix):
                            verification_code = f"{employee_suffix}{phone_suffix}"
                            st.success(f"验证码 {verification_code} 已添加")
                            st.rerun()
                        else:
                            st.error("添加失败，请检查输入")
                    else:
                        st.error("请输入4位数字")
                else:
                    st.error("请填写所有字段")
    
    with col2:
        st.markdown("### 📊 验证码统计")
        
        # 获取所有验证码
        all_codes = verification_mgr.get_all_codes()
        
        if all_codes:
            # 统计信息
            total_codes = len(all_codes)
            active_codes = len([c for c in all_codes if c['status'] == 'active'])
            used_codes = len([c for c in all_codes if c['status'] == 'inactive'])
            
            st.metric("总验证码数", total_codes)
            st.metric("可用验证码", active_codes)
            st.metric("已使用验证码", used_codes)
            
            # 导出功能
            if st.button("📥 导出验证码列表"):
                df = pd.DataFrame(all_codes)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='验证码列表')
                buffer.seek(0)
                
                st.download_button(
                    label="💾 下载Excel文件",
                    data=buffer.getvalue(),
                    file_name=f"验证码列表_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("暂无验证码数据")
    
    # 验证码列表
    st.markdown("### 📋 验证码列表")
    if all_codes:
        # 转换为DataFrame显示
        df = pd.DataFrame(all_codes)
        
        # 格式化显示
        display_df = df.copy()
        display_df['状态'] = display_df['status'].map({'active': '可用', 'inactive': '已使用'})
        display_df['创建时间'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        display_df['使用时间'] = pd.to_datetime(display_df['used_at']).dt.strftime('%Y-%m-%d %H:%M') if 'used_at' in display_df.columns else '未使用'
        
        # 选择要显示的列
        display_columns = ['verification_code', 'employee_id_suffix', 'phone_suffix', '状态', 'used_by', '使用时间', '创建时间']
        display_df = display_df[display_columns]
        display_df.columns = ['验证码', '工号尾号', '手机尾号', '状态', '使用者', '使用时间', '创建时间']
        
        st.dataframe(display_df, use_container_width=True)
        
        # 批量操作
        st.markdown("### 🔧 批量操作")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ 清空所有验证码", type="secondary"):
                if st.checkbox("确认清空所有验证码？此操作不可恢复！"):
                    try:
                        with sqlite3.connect('feedback.db') as conn:
                            cursor = conn.cursor()
                            cursor.execute('DELETE FROM registration_codes')
                            conn.commit()
                        st.success("所有验证码已清空")
                        st.rerun()
                    except Exception as e:
                        st.error(f"清空失败: {e}")
        
        with col2:
            if st.button("🔄 重置已使用验证码", type="secondary"):
                if st.checkbox("确认重置所有已使用的验证码？"):
                    try:
                        with sqlite3.connect('feedback.db') as conn:
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE registration_codes 
                                SET status = "active", used_by = NULL, used_at = NULL
                                WHERE status = "inactive"
                            ''')
                            conn.commit()
                        st.success("已使用验证码已重置")
                        st.rerun()
                    except Exception as e:
                        st.error(f"重置失败: {e}")
    else:
        st.info("暂无验证码数据")
    
    # 使用说明
    with st.expander("📖 使用说明", expanded=False):
        st.markdown("""
        **验证码管理说明：**
        
        1. **Excel文件格式要求：**
           - 必须包含两列：工号牌后4位、手机尾号后4位
           - 系统会自动组合生成8位验证码
        
        2. **验证码规则：**
           - 格式：工号牌后4位 + 手机尾号后4位
           - 例如：工号牌后4位是1234，手机尾号后4位是5678
           - 生成的验证码就是：12345678
        
        3. **安全特性：**
           - 每个验证码只能使用一次
           - 使用后自动标记为已使用状态
           - 支持重置已使用的验证码
        
        4. **管理功能：**
           - 支持Excel批量导入
           - 支持手动添加单个验证码
           - 实时统计验证码使用情况
           - 可导出验证码列表
        """)

if __name__ == "__main__":
    main()
