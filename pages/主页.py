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

# 导入数据库管理器
from db_manager import db

# 导入认证管理器
from auth_manager import auth_manager

# 导入导出管理器
from export_manager import export_manager

# 导入权限控制
from permission_control import require_auth, render_navigation_sidebar

# 定义工单状态常量
PROBLEM_STATUS = {
    'PENDING': '待处理',
    'ASSIGNED': '已派发', 
    'PROCESSING': '处理中',
    'REPLIED': '已处理回复',
    'RESOLVED': '已办结'
}

def get_status_class(status):
    """获取状态对应的CSS类"""
    if PROBLEM_STATUS['PENDING'] in status:
        return 'status-pending'
    elif PROBLEM_STATUS['ASSIGNED'] in status:
        return 'status-assigned'
    elif PROBLEM_STATUS['PROCESSING'] in status:
        return 'status-processing'
    elif PROBLEM_STATUS['REPLIED'] in status:
        return 'status-replied'
    elif PROBLEM_STATUS['RESOLVED'] in status:
        return 'status-resolved'
    else:
        return 'status-pending'  # 默认使用待处理样式

def format_relative_time(created_at_str):
    """格式化相对时间显示"""
    try:
        if not created_at_str:
            return "未知时间"
        
        # 解析创建时间
        if isinstance(created_at_str, str):
            created_time = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
        else:
            created_time = created_at_str
        
        # 获取当前北京时间
        beijing_timezone = pytz.timezone('Asia/Shanghai')
        now = datetime.now(beijing_timezone)
        
        # 如果时间没有时区信息，假设为北京时间
        if created_time.tzinfo is None:
            created_time = beijing_timezone.localize(created_time)
        
        # 计算时间差
        time_diff = now - created_time
        
        # 转换为小时和天数
        hours_diff = time_diff.total_seconds() / 3600
        days_diff = hours_diff / 24
        
        if days_diff >= 1:
            return f"{int(days_diff)}天前"
        elif hours_diff >= 1:
            return f"{int(hours_diff)}小时前"
        else:
            minutes_diff = time_diff.total_seconds() / 60
            if minutes_diff >= 1:
                return f"{int(minutes_diff)}分钟前"
            else:
                return "刚刚"
                
    except Exception as e:
        print(f"格式化相对时间失败: {e}")
        return "未知时间"

def format_absolute_time(created_at_str):
    """格式化绝对时间显示"""
    try:
        if not created_at_str:
            return "未知时间"
        
        # 解析创建时间
        if isinstance(created_at_str, str):
            created_time = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
        else:
            created_time = created_at_str
        
        # 格式化为"年/月/日 XX:XX:XX"
        return created_time.strftime('%Y/%m/%d %H:%M:%S')
                
    except Exception as e:
        print(f"格式化绝对时间失败: {e}")
        return "未知时间"

def format_work_order_id(post_id):
    """格式化工单编号"""
    try:
        # 使用WTXXXXX格式，不足5位前面补0
        return f"WT{str(post_id).zfill(5)}"
    except:
        return f"WT{post_id}"

# 页面配置
st.set_page_config(
    page_title="一线心声",
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
    
    .post-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
        cursor: pointer;
        position: relative;
        overflow: hidden;
    }
    
    .post-card:hover {
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        transform: translateY(-2px);
        border-color: #007bff;
    }
    
    .post-card:active {
        transform: translateY(0);
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    
    .post-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #007bff, #0056b3);
        transform: scaleX(0);
        transition: transform 0.3s ease;
    }
    
    .post-card:hover::before {
        transform: scaleX(1);
    }
    
    .post-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 10px;
        position: relative;
        z-index: 1;
    }
    
    .post-title {
        font-weight: bold;
        color: #1f77b4;
        font-size: 1.1rem;
        flex: 1;
        transition: color 0.3s ease;
        margin-right: 10px;
    }
    
    .post-card:hover .post-title {
        color: #0056b3;
    }
    
    .new-tag {
        background: #007bff;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        margin-left: 10px;
        animation: pulse 2s infinite;
        flex-shrink: 0;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
    
    .post-status {
        color: #666;
        font-size: 0.9rem;
        margin-bottom: 8px;
        background: #f8f9fa;
        padding: 5px 10px;
        border-radius: 5px;
        border-left: 3px solid #007bff;
        position: relative;
        z-index: 1;
    }
    
    .post-content {
        color: #333;
        line-height: 1.6;
        margin-bottom: 10px;
        max-height: 60px;
        overflow: hidden;
        position: relative;
        z-index: 1;
        word-wrap: break-word;
        word-break: break-word;
        white-space: normal;
        text-overflow: ellipsis;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
    }
    
    .post-content.expanded {
        max-height: none;
        -webkit-line-clamp: unset;
    }
    
    .post-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.85rem;
        color: #666;
        margin-top: 10px;
        padding-top: 10px;
        border-top: 1px solid #f0f0f0;
        position: relative;
        z-index: 1;
        flex-wrap: nowrap;
    }
    
    .post-meta {
        display: flex;
        align-items: center;
        gap: 15px;
        flex-wrap: nowrap;
        justify-content: flex-start;
        width: 100%;
    }
    
    .post-meta span {
        display: flex;
        align-items: center;
        gap: 3px;
        padding: 2px 6px;
        border-radius: 4px;
        background: #f8f9fa;
        font-size: 0.8rem;
        color: #555;
        flex-shrink: 0;
    }
    
    .post-meta span:first-child {
        background: #e3f2fd;
        color: #1976d2;
        font-weight: 500;
    }
    
    .post-meta .hashtag {
        margin-left: auto;
        color: #0066cc !important;
        font-weight: bold !important;
        background: #e3f2fd !important;
        border: 1px solid #0066cc;
    }
    
    /* 工单状态标签样式 - 椭圆框格式 */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
        text-align: center;
        border: none;
        margin: 0 2px;
    }
    
    /* 待处理状态 - 橙色 */
    .status-pending {
        background-color: #ff9800;
        color: white;
    }
    
    /* 已派发状态 - 蓝色 */
    .status-assigned {
        background-color: #2196f3;
        color: white;
    }
    
    /* 处理中状态 - 紫色 */
    .status-processing {
        background-color: #9c27b0;
        color: white;
    }
    
    /* 已处理回复状态 - 青色 */
    .status-replied {
        background-color: #00bcd4;
        color: white;
    }
    
    /* 已办结状态 - 绿色 */
    .status-resolved {
        background-color: #4caf50;
        color: white;
    }
    
    .stat-card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        transition: transform 0.3s ease;
    }
    
    .stat-card:hover {
        transform: translateY(-5px);
    }
    
    .category-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 20px;
        margin-top: 20px;
    }
    
    /* 隐藏按钮样式 */
    .stButton > button {
        opacity: 0;
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        cursor: pointer;
        background: transparent;
        border: none;
        z-index: 10;
        padding: 0;
        margin: 0;
    }
    
    /* 卡片容器相对定位 */
    .post-card {
        position: relative;
    }
    
    /* 确保按钮覆盖整个卡片 */
    .stButton {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 10;
    }
    
    /* 移除按钮的默认样式 */
    .stButton > button:hover {
        background: transparent;
        border: none;
    }
    
    .stButton > button:focus {
        background: transparent;
        border: none;
        box-shadow: none;
    }
    
    /* 改善悬停提示样式 */
    .post-card[title]:hover::after {
        content: attr(title);
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.9);
        color: white;
        padding: 10px 15px;
        border-radius: 6px;
        font-size: 13px;
        line-height: 1.4;
        white-space: pre-wrap;
        max-width: 350px;
        max-height: 200px;
        overflow-y: auto;
        z-index: 1000;
        pointer-events: none;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* 添加悬停提示的箭头 */
    .post-card[title]:hover::before {
        content: '';
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: rgba(0, 0, 0, 0.9);
        z-index: 1001;
        pointer-events: none;
    }

/* 确保按钮完全覆盖卡片 */
.stButton {
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    z-index: 10 !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

.stButton > button {
    width: 100% !important;
    height: 100% !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    opacity: 0 !important;
}

.stButton > button:hover {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

.stButton > button:focus {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* 卡片容器相对定位 */
.post-card {
    position: relative !important;
    margin-bottom: 15px !important;
}

/* 确保卡片内容不被按钮遮挡 */
.post-card > * {
    position: relative;
    z-index: 1;
}

/* 点赞/踩按钮样式 */
.like-dislike-buttons {
    position: relative;
    z-index: 2;
}

/* 分页控件样式 */
.pagination-container {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 15px;
    margin: 20px 0;
    border: 1px solid #e9ecef;
}

.pagination-info {
    text-align: center;
    color: #6c757d;
    font-size: 0.9rem;
    padding: 10px;
    background: white;
    border-radius: 6px;
    border: 1px solid #dee2e6;
}

.pagination-stats {
    text-align: right;
    color: #495057;
    font-size: 0.85rem;
    font-weight: 500;
}

/* 分页按钮样式 */
.stButton > button[data-testid="baseButton-secondary"] {
    background: linear-gradient(135deg, #007bff, #0056b3);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    transition: all 0.3s ease;
}

.stButton > button[data-testid="baseButton-secondary"]:hover {
    background: linear-gradient(135deg, #0056b3, #004085);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 123, 255, 0.3);
}

.stButton > button[data-testid="baseButton-secondary"]:disabled {
    background: #6c757d;
    color: #adb5bd;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}

/* 页码跳转输入框样式 */
.stNumberInput > div > div > input {
    border-radius: 6px;
    border: 1px solid #ced4da;
    padding: 8px 12px;
    text-align: center;
    font-weight: 500;
}

.stNumberInput > div > div > input:focus {
    border-color: #007bff;
    box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

/* 整合分页控件样式 */
.pagination-row {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 12px 15px;
    margin: 20px 0 10px 0;
    border: 1px solid #e9ecef;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.pagination-info {
    text-align: center;
    color: #6c757d;
    font-size: 0.9rem;
    font-weight: 500;
}

.pagination-page-info {
    text-align: right;
    color: #495057;
    font-size: 0.85rem;
    font-weight: 500;
}

/* 紧凑的分页按钮样式 */
.stButton > button[data-testid="baseButton-secondary"] {
    background: linear-gradient(135deg, #007bff, #0056b3);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
    font-size: 0.85rem;
    transition: all 0.3s ease;
    min-width: 80px;
}

.stButton > button[data-testid="baseButton-secondary"]:hover {
    background: linear-gradient(135deg, #0056b3, #004085);
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(0, 123, 255, 0.3);
}

.stButton > button[data-testid="baseButton-secondary"]:disabled {
    background: #6c757d;
    color: #adb5bd;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}

/* 紧凑的页码跳转输入框样式 */
.stNumberInput > div > div > input {
    border-radius: 6px;
    border: 1px solid #ced4da;
    padding: 6px 10px;
    text-align: center;
    font-weight: 500;
    font-size: 0.85rem;
    width: 60px;
}

.stNumberInput > div > div > input:focus {
    border-color: #007bff;
    box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

/* 最小化按钮样式 */
.mini-button-row {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    align-items: center;
    padding: 4px 0;
    margin: 2px 0 0 0;
}

.mini-button {
    padding: 4px 8px !important;
    font-size: 0.75rem !important;
    min-height: 28px !important;
    border-radius: 4px !important;
    border: none !important;
    background: #f8f9fa !important;
    color: #666 !important;
    transition: all 0.2s ease !important;
}

.mini-button:hover {
    background: #e9ecef !important;
    border: none !important;
    color: #007bff !important;
    transform: translateY(-1px) !important;
}

.mini-button:active {
    transform: translateY(0) !important;
}

/* 卡片间距优化 */
.post-card {
    margin-bottom: 2px !important;
}

/* 应用最小化样式到特定按钮 */
.mini-button-row .stButton > button {
    padding: 4px 8px !important;
    font-size: 0.75rem !important;
    min-height: 28px !important;
    height: 28px !important;
    border-radius: 4px !important;
    border: none !important;
    background: #f8f9fa !important;
    color: #666 !important;
    transition: all 0.2s ease !important;
    margin: 0 !important;
    opacity: 1 !important;
}

.mini-button-row .stButton > button:hover {
    background: #e9ecef !important;
    border: none !important;
    color: #007bff !important;
    transform: translateY(-1px) !important;
}

.mini-button-row .stButton > button:active {
    transform: translateY(0) !important;
}

.mini-button-row .stButton {
    margin: 0 !important;
    padding: 0 !important;
    position: relative !important;
    width: auto !important;
    height: auto !important;
}

/* 删除按钮特殊样式 */
.delete-button {
    background: #f8d7da !important;
    color: #721c24 !important;
}

.delete-button:hover {
    background: #f5c6cb !important;
    color: #721c24 !important;
    border: none !important;
}

/* 针对删除按钮的特殊样式 */
.mini-button-row .stButton:last-child > button {
    background: #f8d7da !important;
    color: #721c24 !important;
}

.mini-button-row .stButton:last-child > button:hover {
    background: #f5c6cb !important;
    color: #721c24 !important;
    border: none !important;
}

/* 确认删除状态的按钮样式 */
.confirm-delete-button {
    background: #dc3545 !important;
    color: white !important;
    animation: blink 1s infinite !important;
}

@keyframes blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0.7; }
}
</style>
""", unsafe_allow_html=True)

# 使用数据库管理器加载真实数据
def load_real_posts_data():
    """从数据库加载真实的帖子数据"""
    return db.get_all_problems()

# 左侧边栏
def render_sidebar():
    """渲染左侧边栏"""
    st.sidebar.title("📊 数据概览")
    
    # 获取实时统计数据
    stats = db.get_statistics()
    total_posts = stats.get('total_problems', 0)
    today_new = stats.get('today_new', 0)
    week_new = stats.get('week_new', 0)
    
    # 统计信息
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.metric("📈 总发帖数", total_posts, f"+{week_new}")
    with col2:
        st.metric("📅 今日新增", today_new, f"+{today_new}")
    
    st.sidebar.divider()
    
    # 快速筛选
    st.sidebar.subheader("🔍 快速筛选")
    category_filter = st.sidebar.selectbox(
        "📂 问题分类",
        ["全部", "网络运维", "后勤服务类", "职工教育成长类", 
         "企业文化建设类", "发展经营类", 
         "生活福利类", "劳动保护类", "薪酬晋升类", "民主管理类", "其他方面"]
    )
    
    status_filter = st.sidebar.selectbox(
        "🔄 处理状态",
        ["全部", "待处理", "处理中", "已完结"]
    )
    
    time_filter = st.sidebar.selectbox(
        "⏰ 时间范围",
        ["全部", "今天", "本周", "本月", "最近30天"]
    )
    
    # 添加单位筛选
    unit_filter = st.sidebar.selectbox(
        "🏢 单位筛选",
        ["全部", "网络部", "综合部", "人力部", "市场部", "集客部", 
         "全业务支撑中心", "客体部", "党建部", "财务部", "工会", "纪委办",
         "船山", "射洪", "蓬溪", "大英", "安居"]
    )
    
    st.sidebar.divider()
    
    # 快速操作 - 补充完善
    st.sidebar.subheader("⚡ 快速操作")
    
    # 发布新问题
    if st.sidebar.button("📝 发布新问题", type="primary", use_container_width=True):
        st.info("发布问题功能开发中...")
    
    # 工单调度（仅对有权限的用户显示）
    user_info = st.session_state.get('user_info', {})
    user_role = user_info.get('role', 'user')
    
    if user_role in ['admin', 'manager', 'processor']:
        if st.sidebar.button("📋 工单调度", use_container_width=True):
            st.switch_page("pages/工单调度.py")
    
    # 查看统计
    if st.sidebar.button("📊 查看统计", use_container_width=True):
        st.info("统计分析功能开发中...")
    
    # 搜索问题
    if st.sidebar.button("🔍 搜索问题", use_container_width=True):
        st.session_state.show_search = True
    
    # 导出数据
    if st.sidebar.button("📋 导出数据", use_container_width=True):
        st.info("导出功能开发中...")
    
    # 批量操作
    if st.sidebar.button("🔄 批量处理", use_container_width=True):
        st.info("批量处理功能开发中...")
    
    # 系统设置
    if st.sidebar.button("⚙️ 系统设置", use_container_width=True):
        st.info("系统设置功能开发中...")
    
    # 帮助文档
    if st.sidebar.button("❓ 帮助文档", use_container_width=True):
        st.info("帮助文档功能开发中...")
    
    return category_filter, status_filter, time_filter, unit_filter

# Tab1: 全部发帖
def render_all_posts_tab(posts_data):
    """渲染全部发帖选项卡"""
    st.subheader("📋 全部发帖")
    
    # 搜索和筛选
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        search_term = st.text_input("🔍 搜索问题", placeholder="输入关键词搜索...")
    with col2:
        sort_by = st.selectbox("📊 排序方式", ["最新发布", "最多浏览", "最多评论"])
    with col3:
        filter_new = st.checkbox("🆕 仅显示新问题")
    with col4:
        # 导出功能
        if st.button("📤 导出Excel", use_container_width=True):
            if posts_data:
                with st.spinner("正在导出数据..."):
                    file_path = export_manager.export_problems_to_excel(posts_data)
                    if file_path:
                        st.success("导出成功！")
                        # 生成下载链接
                        download_link = export_manager.get_download_link(file_path, "📥 点击下载Excel文件")
                        st.markdown(download_link, unsafe_allow_html=True)
                    else:
                        st.error("导出失败，请重试")
            else:
                st.warning("暂无数据可导出")
    
    st.divider()
    
    # 检查是否有数据
    if not posts_data:
        st.warning("📭 暂无数据，请先发布一些问题")
        return
    
    # 应用筛选条件
    filtered_posts = []
    for post in posts_data:
        # 应用搜索筛选
        if search_term and search_term.lower() not in post["title"].lower():
            continue
        # 应用新问题筛选
        if filter_new and not post["is_new"]:
            continue
        filtered_posts.append(post)
    
    # 应用排序
    if sort_by == "最新发布":
        filtered_posts.sort(key=lambda x: x["created_at"], reverse=True)
    elif sort_by == "最多浏览":
        filtered_posts.sort(key=lambda x: x["views"], reverse=True)
    elif sort_by == "最多评论":
        filtered_posts.sort(key=lambda x: x["comments"], reverse=True)
    
    # 分页设置
    posts_per_page = 20
    total_posts = len(filtered_posts)
    total_pages = (total_posts + posts_per_page - 1) // posts_per_page  # 向上取整
    
    # 初始化当前页码
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 1
    
    # 计算当前页的数据范围
    start_idx = (st.session_state.current_page - 1) * posts_per_page
    end_idx = min(start_idx + posts_per_page, total_posts)
    current_page_posts = filtered_posts[start_idx:end_idx]
    
    # 显示当前页的发帖列表
    for post in current_page_posts:
        # 安全获取和处理数据
        try:
            # 获取基本信息
            post_id = post.get('id', 0)
            title = str(post.get('title', '')).strip()
            content = str(post.get('description', '')).strip()  # 修复：使用description字段
            author = str(post.get('author', '')).strip()
            created_at = str(post.get('created_at', '')).strip()
            work_order = format_work_order_id(post_id) # 使用格式化工单号
            status = str(post.get('status', '')).strip()
            comments = int(post.get('comments', 0))
            likes = int(post.get('likes', 0))
            dislikes = int(post.get('dislikes', 0))
            views = int(post.get('views', 0))
            category = str(post.get('category', '')).strip()  # 修复：使用category字段
            is_new = bool(post.get('is_new', False))
            
            # 处理时间显示
            post_time = format_relative_time(created_at) # 使用相对时间
            
            # 处理hashtag显示（使用category）
            hashtag = f"#{category}#" if category else "#未分类#"
            
            # 彻底清理内容中的HTML - 强化版
            if content:
                # 使用数据库管理器的清理方法
                from db_manager import DatabaseManager
                temp_db = DatabaseManager()
                content = temp_db._clean_content_thoroughly(content)
            
            # 确保内容不为空
            if not content:
                content = "内容加载中..."
            
            # 安全处理所有字段，防止HTML注入
            title_safe = html.escape(title)
            content_safe = html.escape(content)
            author_safe = html.escape(author)
            post_time_safe = html.escape(post_time)
            created_at_safe = html.escape(created_at)
            work_order_safe = html.escape(work_order)
            status_safe = html.escape(status)
            hashtag_safe = html.escape(hashtag)
            
            # 截取显示内容（限制长度）
            display_content = content_safe[:150] + ('...' if len(content_safe) > 150 else '')
            
            # 创建发帖卡片容器
            with st.container():
                # 创建可点击的发帖卡片
                card_html = f"""
                <div class="post-card" style="position: relative;">
                    <div class="post-header">
                        <div class="post-title">
                            {title_safe}
                            {'<span class="new-tag">New</span>' if is_new else ''}
                        </div>
                    </div>
                    <div class="post-content">{display_content}</div>
                    <div class="post-footer">
                        <div class="post-meta">
                            <span>👤 {author_safe}</span>
                            <span>🕒 {post_time_safe}</span>
                            <span>📅 {format_absolute_time(created_at)}</span>
                            <span>🔢 {work_order_safe}</span>
                            <span class="status-badge {get_status_class(status_safe)}">{status_safe}</span>
                            <span>💬 {comments}</span>
                            <span>👍 {likes}</span>
                            <span>👎 {dislikes}</span>
                            <span>👁️ {views}</span>
                            <span class="hashtag" style="color: #0066cc !important; font-weight: bold !important; background: #e3f2fd; padding: 2px 8px; border-radius: 12px; border: 1px solid #0066cc; margin-left: auto;">{hashtag_safe}</span>
                        </div>
                    </div>
                </div>
                """
                
                # === 终极安全渲染逻辑 ===
                # 强制验证display_content
                if "<" in display_content or ">" in display_content:
                    st.error(f"🚨 发现HTML内容，强制清理: {display_content[:50]}...")
                    # 强制重新清理
                    clean_content = title + " " + content[:100]  # 使用原始安全内容
                    import re
                    clean_content = re.sub(r'<[^>]*>', '', clean_content)  # 移除所有HTML标签
                    clean_content = clean_content.strip()
                    display_content = clean_content[:150] + ('...' if len(clean_content) > 150 else '')
                
                # 最终安全检查
                display_content = display_content.replace('<', '&lt;').replace('>', '&gt;')
                
                # 使用简化的安全HTML结构
                simple_card_html = f"""
                <div class="post-card" style="border: 1px solid #ddd; padding: 15px; margin: 2px 0 0 0; border-radius: 8px; background: #f9f9f9; position: relative;" title="{content_safe}">
                    <div style="font-weight: bold; margin-bottom: 8px; color: #0066cc;">
                        {title_safe} {'<span style="background: #ff4444; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em; margin-left: 8px;">New</span>' if is_new else ''}
                    </div>
                    <div style="margin: 8px 0; color: #666; line-height: 1.4;">
                        {display_content}
                    </div>
                    <div style="font-size: 0.9em; color: #888; border-top: 1px solid #eee; padding-top: 8px; margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <span>👤 {author_safe}</span>
                            <span>🕒 {post_time_safe}</span>
                            <span>📅 {format_absolute_time(created_at)}</span>
                            <span>🔢 {work_order_safe}</span>
                            <span class="status-badge {get_status_class(status_safe)}">{status_safe}</span>
                        </div>
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <span>💬 {comments}</span>
                            <span>👍 {likes}</span>
                            <span>👎 {dislikes}</span>
                            <span>👁️ {views}</span>
                            <span style="color: #0066cc; font-weight: bold; background: #e3f2fd; padding: 2px 8px; border-radius: 12px; border: 1px solid #0066cc;">{hashtag_safe}</span>
                        </div>
                    </div>
                </div>
                """
                
                st.markdown(simple_card_html, unsafe_allow_html=True)
                
                # 获取当前用户信息和角色
                user_info = st.session_state.get('user_info', {})
                user_role = user_info.get('role', 'user')
                is_admin = user_role == 'admin'
                
                # 最小化按钮行 - 紧贴卡片右侧
                with st.container():
                    st.markdown('<div class="mini-button-row">', unsafe_allow_html=True)
                    
                    # 根据是否为admin调整布局
                    if is_admin:
                        col1, col2, col3, col4, col5 = st.columns([8, 1, 1, 1, 1])
                    else:
                        col1, col2, col3, col4 = st.columns([6, 1, 1, 1])
                    
                    with col1:
                        st.empty()  # 空白占位，推按钮到右侧
                    
                    with col2:
                        if st.button("👍", key=f"like_{post_id}", help=f"点赞 ({likes})", use_container_width=True):
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
                            
                            success = db.add_reaction(post_id, user_id, 'like')
                            if success:
                                st.success("点赞成功！")
                                # 强制刷新页面数据
                                st.rerun()
                            else:
                                st.error("点赞失败，请重试")
                    
                    with col3:
                        if st.button("👎", key=f"dislike_{post_id}", help=f"踩 ({dislikes})", use_container_width=True):
                            # 改进用户ID获取逻辑
                            user_id = None
                            user_info = st.session_state.get('user_info', {})
                            
                            if user_info and 'id' in user_info:
                                user_id = user_info['id']
                            else:
                                st.error("请先登录后再踩")
                                return
                            
                            success = db.add_reaction(post_id, user_id, 'dislike')
                            if success:
                                st.success("踩成功！")
                                # 强制刷新页面数据
                                st.rerun()
                            else:
                                st.error("踩失败，请重试")
                    
                    with col4:
                        if st.button("📋", key=f"card_{post_id}", help="查看详情", use_container_width=True):
                            st.session_state.selected_post_id = post_id
                            st.switch_page("pages/问题详情.py")
                    
                    # 仅为admin显示删除按钮
                    if is_admin:
                        with col5:
                            # 检查是否已经处于确认状态
                            confirm_key = f'confirm_delete_{post_id}'
                            is_confirming = st.session_state.get(confirm_key, False)
                            
                            button_text = "❌" if not is_confirming else "确认删除"
                            button_help = "删除问题" if not is_confirming else "点击确认删除"
                            
                            if st.button(button_text, key=f"delete_{post_id}", help=button_help, use_container_width=True):
                                if not is_confirming:
                                    # 首次点击，进入确认状态
                                    st.session_state[confirm_key] = True
                                    st.warning(f"确认要删除问题「{title_safe}」吗？再次点击红色按钮确认。")
                                    st.rerun()
                                else:
                                    # 第二次点击，执行删除
                                    operator = user_info.get('real_name', 'admin')
                                    
                                    # 双重权限检查
                                    from auth_manager import auth_manager
                                    if auth_manager.check_permission(user_role, 'delete_problems'):
                                        success = db.delete_problem(post_id, operator)
                                        if success:
                                            st.success(f"问题 {post_id} 已删除")
                                            # 清除确认状态
                                            st.session_state[confirm_key] = False
                                            st.rerun()
                                        else:
                                            st.error("删除失败，请稍后重试")
                                            st.session_state[confirm_key] = False
                                    else:
                                        st.error("权限不足，无法删除问题")
                                        st.session_state[confirm_key] = False
                    
                    st.markdown('</div>', unsafe_allow_html=True)
        
        except Exception as e:
            # 如果渲染出错，显示错误信息
            st.error(f"渲染问题卡片时出错: {e}")
            st.write("问题数据:", post)
            continue
    
    # 整合的分页控件 - 底部一行
    if total_pages > 1:
        st.divider()
        col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
        
        with col1:
            if st.button("◀️ 上一页", disabled=st.session_state.current_page <= 1, key="prev_page"):
                st.session_state.current_page -= 1
                st.rerun()
        
        with col2:
            if st.button("下一页 ▶️", disabled=st.session_state.current_page >= total_pages, key="next_page"):
                st.session_state.current_page += 1
                st.rerun()
        
        with col3:
            st.markdown(f"<div style='text-align: center; color: #666; font-size: 0.9rem;'>显示第 {start_idx + 1}-{end_idx} 条，共 {total_posts} 条记录</div>", unsafe_allow_html=True)
        
        with col4:
            # 页码跳转
            page_input = st.number_input("跳转到", min_value=1, max_value=total_pages, value=st.session_state.current_page, key="page_jump")
            if page_input != st.session_state.current_page:
                st.session_state.current_page = page_input
                st.rerun()
        
        with col5:
            st.markdown(f"<div style='text-align: right; color: #666; font-size: 0.9rem;'>第 {st.session_state.current_page} 页，共 {total_pages} 页</div>", unsafe_allow_html=True)

# Tab2: 我要发声
def render_speak_up_tab():
    """渲染我要发声选项卡"""
    st.subheader("我要发声")
    
    # 初始化session_state
    if 'is_anonymous' not in st.session_state:
        st.session_state.is_anonymous = False
    
    # 匿名选项放在表单外部，这样可以实时更新界面
    is_anonymous = st.checkbox("匿名发布", value=st.session_state.is_anonymous, key="anonymous_checkbox")
    st.session_state.is_anonymous = is_anonymous
    
    # 获取当前用户信息
    user_info = st.session_state.get('user_info', {})
    
    # 添加发布问题的表单
    with st.form("problem_form", clear_on_submit=True):
        st.markdown("### 问题信息")
        
        problem_category = st.selectbox(
            "问题分类 *",
            ["发展经营类", "企业文化建设类", "后勤服务类", 
             "职工教育成长类", "生活福利类", "劳动保护类", "薪酬晋升类", 
             "民主管理类", "其他方面"],
            index=None,
            placeholder="请选择分类"
        )
        
        problem_title = st.text_input(
            "问题标题 *",
            placeholder="请简要描述您的问题..."
        )
        
        problem_description = st.text_area(
            "问题详细描述 *", 
            placeholder="请详细描述您遇到的问题、影响和建议解决方案...",
            height=200
        )
        
        # 将附件上传移到问题信息区域
        uploaded_files = st.file_uploader(
            "上传附件", 
            accept_multiple_files=True,
            type=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']
        )
        
        # 首响单位选择
        st.markdown("### 工单分配")
        
        # 获取部门列表
        departments = db.get_all_departments()
        department_options = ["未定"] + departments  # 添加"未定"选项
        
        # 使用列布局将标签和下拉框放在同一行
        col1, col2 = st.columns([1, 5])
        with col1:
            st.markdown("首响部门：")
        with col2:
            response_department = st.selectbox(
                "首响部门选择",
                department_options,
                index=None,
                placeholder="请选择首响部门",
                label_visibility="collapsed"
            )
        
        # 如果选择了具体部门，显示该部门的处理人信息
        if response_department and response_department != "未定":
            processors = db.get_department_processors(response_department)
            if processors:
                st.info(f"📋 该问题将自动分配给 {response_department} 部门的处理人处理")
                with st.expander(f"查看 {response_department} 部门处理人"):
                    for processor in processors:
                        st.write(f"👤 {processor['real_name']} ({processor['username']})")
                        if processor.get('email'):
                            st.write(f"📧 {processor['email']}")
                        if processor.get('phone'):
                            st.write(f"📞 {processor['phone']}")
            else:
                st.warning(f"⚠️ {response_department} 部门暂无处理人，问题将等待分配")
        elif response_department == "未定":
            st.info("📋 该问题将自动流转至调度中心，由调度中心管理员处理")
        
        # 根据匿名状态显示用户信息
        if not st.session_state.is_anonymous:
            # 实名发布：显示用户信息（只读）
            st.markdown("### 发布者信息")
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("姓名", value=user_info.get('real_name', ''), disabled=True)
            with col2:
                st.text_input("联系方式", value=user_info.get('phone', ''), disabled=True)
            
            # 使用用户登录时的信息
            author_name = user_info.get('real_name', '')
            contact_info = user_info.get('phone', '')
        else:
            # 匿名发布：隐藏用户信息
            st.info("已选择匿名发布，将隐藏您的个人信息")
            author_name = "匿名用户"
            contact_info = ""
        
        # 修改按钮文本
        submitted = st.form_submit_button("发布信息", use_container_width=True)
        
        if submitted:
            if problem_category is None or not problem_title or not problem_description:
                st.error("请填写必填项！")
            elif not st.session_state.is_anonymous and not author_name:
                st.error("用户信息获取失败，请重新登录！")
            else:
                # 根据规则1.1和1.2确定response_department
                if response_department == "未定" or response_department is None:
                    # 规则1.1：未指定首响部门，自动流转至调度中心
                    final_response_department = "调度中心"
                else:
                    # 规则1.2：指定了具体部门，由相应部门处理
                    final_response_department = response_department
                
                # 保存问题到数据库
                success, result = db.save_problem(
                    problem_title.strip(),
                    problem_category,
                    problem_description.strip(),
                    author_name.strip(),
                    contact_info.strip() if contact_info else "",
                    user_info.get('department', ''),  # 添加用户部门信息
                    uploaded_files=uploaded_files,  # 传递上传的文件
                    response_department=final_response_department  # 添加首响单位
                )
                
                if success:
                    st.success(f"发布成功！编号：{result}")
                    st.rerun()
                else:
                    st.error(f"发布失败：{result}")

# Tab3: 分领域统计
def render_category_stats_tab(category_stats):
    """渲染分领域统计选项卡"""
    st.subheader("分领域统计")
    
    # 检查数据是否为空
    if not category_stats:
        st.warning("暂无统计数据，请先发布一些问题")
        return
    
    # 统计概览
    total_posts = sum(category_stats.values())
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总问题数", total_posts)
    with col2:
        st.metric("已完结", int(total_posts * 0.75))
    with col3:
        st.metric("处理中", int(total_posts * 0.15))
    with col4:
        st.metric("待处理", int(total_posts * 0.10))
    
    st.divider()
    
    # 分类统计图表
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 柱状图
        fig_bar = px.bar(
            x=list(category_stats.keys()),
            y=list(category_stats.values()),
            title="各领域问题分布",
            labels={'x': '问题领域', 'y': '问题数量'},
            color=list(category_stats.values()),
            color_continuous_scale='Blues'
        )
        fig_bar.update_layout(height=400)
        st.plotly_chart(fig_bar, use_container_width=True)
    
    with col2:
        # 饼图
        fig_pie = px.pie(
            values=list(category_stats.values()),
            names=list(category_stats.keys()),
            title="问题领域占比"
        )
        fig_pie.update_layout(height=400)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    # 详细统计表格
    st.markdown("### 详细统计")
    stats_df = pd.DataFrame([
        {"领域": category, "问题数量": count, "占比": f"{count/total_posts*100:.1f}%"}
        for category, count in category_stats.items()
    ])
    st.dataframe(stats_df, use_container_width=True)

# Tab4: 分单位统计
def render_department_stats_tab(department_stats):
    """渲染分单位统计选项卡"""
    st.subheader("分单位统计")
    
    # 检查数据是否为空
    if not department_stats:
        st.warning("暂无统计数据，请先发布一些问题")
        return
    
    # 统计概览
    total_posts = sum(department_stats.values())
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总问题数", total_posts)
    with col2:
        st.metric("涉及部门", len(department_stats))
    with col3:
        st.metric("平均问题数", f"{total_posts/len(department_stats):.1f}")
    with col4:
        st.metric("最高问题数", max(department_stats.values()))
    
    st.divider()
    
    # 部门统计图表
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 水平柱状图
        fig_bar = px.bar(
            x=list(department_stats.values()),
            y=list(department_stats.keys()),
            orientation='h',
            title="各部门问题数量",
            labels={'x': '问题数量', 'y': '部门'},
            color=list(department_stats.values()),
            color_continuous_scale='Greens'
        )
        fig_bar.update_layout(height=500)
        st.plotly_chart(fig_bar, use_container_width=True)
    
    with col2:
        # 饼图
        fig_pie = px.pie(
            values=list(department_stats.values()),
            names=list(department_stats.keys()),
            title="部门问题占比"
        )
        fig_pie.update_layout(height=400)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    # 详细统计表格
    st.markdown("### 部门详细统计")
    stats_df = pd.DataFrame([
        {"部门": dept, "问题数量": count, "占比": f"{count/total_posts*100:.1f}%"}
        for dept, count in department_stats.items()
    ]).sort_values("问题数量", ascending=False)
    st.dataframe(stats_df, use_container_width=True)

# 主函数
@require_auth
def main():
    """主函数"""
    
    # 清除缓存以确保数据更新（兼容不同版本的Streamlit）
    try:
        if hasattr(st, 'cache_data'):
            st.cache_data.clear()
        if hasattr(st, 'cache_resource'):
            st.cache_resource.clear()
    except:
        # 如果缓存清除失败，继续执行
        pass
    
    # 渲染权限控制导航侧边栏
    render_navigation_sidebar()
    
    # 页面标题
    st.markdown('<h1 class="main-header">一线心声</h1>', unsafe_allow_html=True)
    
    # 渲染左侧边栏
    category_filter, status_filter, time_filter, unit_filter = render_sidebar()
    
    # 构建筛选条件
    filters = {}
    if category_filter and category_filter != "全部":
        filters['category'] = category_filter
    if status_filter and status_filter != "全部":
        filters['status'] = status_filter
    if time_filter and time_filter != "全部":
        filters['time_range'] = time_filter
    if unit_filter and unit_filter != "全部":
        filters['unit'] = unit_filter  # 改为unit，避免与department字段冲突
    
    # 加载真实数据并应用筛选
    posts_data = db.get_all_problems(filters)
    
    # 获取统计数据
    stats = db.get_statistics()
    category_stats = stats.get('category_stats', {})
    department_stats = stats.get('department_stats', {})
    
    # 主内容区域
    with st.container():
        # 选项卡
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 全部发帖", 
            "🎤 我要发声", 
            "📊 分领域统计", 
            "🏢 分单位统计"
        ])
        
        with tab1:
            render_all_posts_tab(posts_data)
        
        with tab2:
            render_speak_up_tab()
        
        with tab3:
            render_category_stats_tab(category_stats)
        
        with tab4:
            render_department_stats_tab(department_stats)
    
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