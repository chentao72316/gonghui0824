#!/usr/bin/env python3
"""
数据导出管理器
支持Excel和PDF格式的数据导出功能
"""

import pandas as pd
from datetime import datetime, timedelta
import os
from typing import List, Dict, Any, Optional
from db_manager import db
import io
import base64
import pytz

class ExportManager:
    """数据导出管理类"""
    
    def __init__(self):
        self.export_dir = "exports"
        self._ensure_export_dir()
    
    def _ensure_export_dir(self):
        """确保导出目录存在"""
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir)
    
    def export_problems_to_excel(self, problems_data: List[Dict], filename: Optional[str] = None) -> str:
        """
        将问题列表导出为Excel文件
        
        Args:
            problems_data: 问题数据列表
            filename: 文件名（可选）
            
        Returns:
            文件路径
        """
        try:
            # 准备导出数据
            export_data = []
            for problem in problems_data:
                export_data.append({
                    'ID': problem.get('id', ''),
                    '标题': problem.get('title', ''),
                    '分类': problem.get('category', ''),
                    '状态': problem.get('status', ''),
                    '优先级': problem.get('priority', ''),
                    '发布人': problem.get('author', ''),
                    '发布时间': problem.get('created_at', ''),
                    '更新时间': problem.get('updated_at', ''),
                    '处理人': problem.get('processing_person', ''),
                    '处理单位': problem.get('processing_unit', ''),
                    '描述': problem.get('description', '')
                })
            
            # 创建DataFrame
            df = pd.DataFrame(export_data)
            
            # 生成文件名
            if not filename:
                # 获取当前北京时间
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                now_beijing = datetime.now(beijing_timezone)
                timestamp = now_beijing.strftime("%Y%m%d_%H%M%S")
                filename = f"问题列表_{timestamp}.xlsx"
            
            file_path = os.path.join(self.export_dir, filename)
            
            # 创建Excel写入器
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # 写入主数据
                df.to_excel(writer, sheet_name='问题列表', index=False)
                
                # 获取统计数据
                stats = db.get_statistics()
                
                # 写入统计信息
                if stats:
                    # 分类统计
                    category_stats = stats.get('category_stats', {})
                    if category_stats:
                        category_df = pd.DataFrame([
                            {'分类': k, '数量': v} for k, v in category_stats.items()
                        ])
                        category_df.to_excel(writer, sheet_name='分类统计', index=False)
                    
                    # 部门统计
                    department_stats = stats.get('department_stats', {})
                    if department_stats:
                        department_df = pd.DataFrame([
                            {'部门': k, '数量': v} for k, v in department_stats.items()
                        ])
                        department_df.to_excel(writer, sheet_name='部门统计', index=False)
                    
                    # 状态统计
                    status_stats = stats.get('status_stats', {})
                    if status_stats:
                        status_df = pd.DataFrame([
                            {'状态': k, '数量': v} for k, v in status_stats.items()
                        ])
                        status_df.to_excel(writer, sheet_name='状态统计', index=False)
            
            return file_path
            
        except Exception as e:
            # st.error(f"导出Excel失败: {str(e)}") # Removed st.error
            return None
    
    def export_problem_detail_to_pdf(self, problem_id: int, filename: Optional[str] = None) -> str:
        """
        将单个问题详情导出为PDF报告
        
        Args:
            problem_id: 问题ID
            filename: 文件名（可选）
            
        Returns:
            文件路径
        """
        try:
            # 获取问题详情
            problem = db.get_problem_by_id(problem_id)
            if not problem:
                # st.error("问题不存在") # Removed st.error
                return None
            
            # 获取相关数据
            comments = db.get_comments(problem_id)
            processing_records = db.get_processing_records(problem_id)
            files = db.get_problem_files(problem_id)
            
            # 生成文件名
            if not filename:
                # 获取当前北京时间
                beijing_timezone = pytz.timezone('Asia/Shanghai')
                now_beijing = datetime.now(beijing_timezone)
                timestamp = now_beijing.strftime("%Y%m%d_%H%M%S")
                filename = f"问题详情_{problem_id}_{timestamp}.pdf"
            
            file_path = os.path.join(self.export_dir, filename)
            
            # 使用reportlab生成真正的PDF文件
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
                from reportlab.lib import colors
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                from reportlab.pdfbase.cidfonts import UnicodeCIDFont
                
                # 注册中文字体
                try:
                    # 尝试注册系统中文字体
                    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                    chinese_font = 'STSong-Light'
                except:
                    try:
                        # 备用方案：使用系统默认字体
                        pdfmetrics.registerFont(UnicodeCIDFont('SimSun'))
                        chinese_font = 'SimSun'
                    except:
                        # 如果都失败，使用默认字体
                        chinese_font = 'Helvetica'
                        # st.warning("未找到中文字体，中文可能显示为方框") # Removed st.warning
                
                # 创建PDF文档
                doc = SimpleDocTemplate(file_path, pagesize=A4)
                story = []
                
                # 获取样式并设置中文字体
                styles = getSampleStyleSheet()
                
                # 自定义样式，支持中文
                title_style = ParagraphStyle(
                    'CustomTitle',
                    parent=styles['Heading1'],
                    fontSize=16,
                    spaceAfter=20,
                    alignment=1,  # 居中
                    fontName=chinese_font
                )
                
                heading_style = ParagraphStyle(
                    'CustomHeading',
                    parent=styles['Heading2'],
                    fontSize=14,
                    spaceAfter=10,
                    fontName=chinese_font
                )
                
                normal_style = ParagraphStyle(
                    'CustomNormal',
                    parent=styles['Normal'],
                    fontSize=10,
                    spaceAfter=5,
                    fontName=chinese_font
                )
                
                # 添加标题
                story.append(Paragraph("问题详情报告", title_style))
                story.append(Spacer(1, 20))
                
                # 添加基本信息
                story.append(Paragraph("基本信息", heading_style))
                story.append(Spacer(1, 10))
                
                # 基本信息表格
                basic_data = [
                    ['问题ID', str(problem.get('id', ''))],
                    ['标题', problem.get('title', '')],
                    ['分类', problem.get('category', '')],
                    ['状态', problem.get('status', '')],
                    ['优先级', problem.get('priority', '普通')],
                    ['发布人', problem.get('author', '')],
                    ['发布时间', str(problem.get('created_at', ''))],
                    ['描述', problem.get('description', '')]
                ]
                
                basic_table = Table(basic_data, colWidths=[1.5*inch, 4*inch])
                basic_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), chinese_font),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('FONTNAME', (0, 1), (-1, -1), chinese_font),
                    ('FONTSIZE', (0, 1), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                story.append(basic_table)
                story.append(Spacer(1, 20))
                
                # 添加处理记录
                if processing_records:
                    story.append(Paragraph("处理记录", heading_style))
                    story.append(Spacer(1, 10))
                    
                    for record in processing_records:
                        # 安全地访问记录字段
                        processor = record.get('processor', '') if hasattr(record, 'get') else (record['processor'] if 'processor' in record.keys() else '')
                        created_at = record.get('created_at', '') if hasattr(record, 'get') else (record['created_at'] if 'created_at' in record.keys() else '')
                        measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
                        
                        record_text = f"<b>处理人:</b> {processor} | <b>时间:</b> {created_at} | <b>措施:</b> {measure}"
                        story.append(Paragraph(record_text, normal_style))
                        story.append(Spacer(1, 5))
                    story.append(Spacer(1, 20))
                
                # 添加评论
                if comments:
                    story.append(Paragraph("评论记录", heading_style))
                    story.append(Spacer(1, 10))
                    
                    for comment in comments:
                        comment_text = f"<b>{comment.get('author', '')}</b> ({comment.get('created_at', '')}): {comment.get('content', '')}"
                        story.append(Paragraph(comment_text, normal_style))
                        story.append(Spacer(1, 5))
                    story.append(Spacer(1, 20))
                
                # 添加附件信息
                if files:
                    story.append(Paragraph("附件文件", heading_style))
                    story.append(Spacer(1, 10))
                    
                    for file_info in files:
                        file_text = f"文件名: {file_info.get('file_name', '')} | 大小: {file_info.get('file_size', '')} bytes"
                        story.append(Paragraph(file_text, normal_style))
                        story.append(Spacer(1, 5))
                
                # 生成PDF
                doc.build(story)
                return file_path
                
            except ImportError:
                # 如果没有reportlab，回退到HTML方式
                # st.warning("未安装reportlab库，将生成HTML格式文件") # Removed st.warning
                pdf_content = self._generate_pdf_content(problem, comments, processing_records, files)
                
                # 保存HTML文件
                html_file_path = file_path.replace('.pdf', '.html')
                with open(html_file_path, 'w', encoding='utf-8') as f:
                    f.write(pdf_content)
                
                return html_file_path
                
            except Exception as e:
                # 如果PDF生成失败，回退到HTML方式
                # st.warning(f"PDF生成失败: {str(e)}，将生成HTML格式文件") # Removed st.warning
                pdf_content = self._generate_pdf_content(problem, comments, processing_records, files)
                
                # 保存HTML文件
                html_file_path = file_path.replace('.pdf', '.html')
                with open(html_file_path, 'w', encoding='utf-8') as f:
                    f.write(pdf_content)
                
                return html_file_path
            
        except Exception as e:
            # st.error(f"导出PDF失败: {str(e)}") # Removed st.error
            return None
    
    def _generate_pdf_content(self, problem: Dict, comments: List[Dict], 
                            processing_records: List[Dict], files: List[Dict]) -> str:
        """生成PDF内容"""
        
        # 获取当前北京时间
        beijing_timezone = pytz.timezone('Asia/Shanghai')
        now_beijing = datetime.now(beijing_timezone)
        current_time = now_beijing.strftime("%Y-%m-%d %H:%M:%S")
        
        content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>问题详情报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .section {{ margin-bottom: 20px; }}
        .section-title {{ font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }}
        .info-row {{ margin-bottom: 8px; }}
        .label {{ font-weight: bold; color: #666; }}
        .value {{ color: #333; }}
        .comment {{ background: #f9f9f9; padding: 10px; margin-bottom: 10px; border-radius: 5px; }}
        .processing {{ background: #e3f2fd; padding: 10px; margin-bottom: 10px; border-radius: 5px; }}
        .file {{ background: #f3e5f5; padding: 8px; margin-bottom: 5px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>问题详情报告</h1>
        <p>生成时间: {current_time}</p>
    </div>
    
    <div class="section">
        <div class="section-title">基本信息</div>
        <div class="info-row">
            <span class="label">问题ID:</span>
            <span class="value">{problem.get('id', '')}</span>
        </div>
        <div class="info-row">
            <span class="label">标题:</span>
            <span class="value">{problem.get('title', '')}</span>
        </div>
        <div class="info-row">
            <span class="label">分类:</span>
            <span class="value">{problem.get('category', '')}</span>
        </div>
        <div class="info-row">
            <span class="label">状态:</span>
            <span class="value">{problem.get('status', '')}</span>
        </div>
        <div class="info-row">
            <span class="label">优先级:</span>
            <span class="value">{problem.get('priority', '')}</span>
        </div>
        <div class="info-row">
            <span class="label">发布人:</span>
            <span class="value">{problem.get('author', '')}</span>
        </div>
        <div class="info-row">
            <span class="label">发布时间:</span>
            <span class="value">{problem.get('created_at', '')}</span>
        </div>
    </div>
    
    <div class="section">
        <div class="section-title">问题描述</div>
        <div class="value">{problem.get('description', '')}</div>
    </div>
"""
        
        # 添加留言
        if comments:
            content += """
    <div class="section">
        <div class="section-title">留言记录</div>
"""
            for comment in comments:
                content += f"""
        <div class="comment">
            <div><strong>{comment.get('author', '')}</strong> - {comment.get('created_at', '')}</div>
            <div>{comment.get('content', '')}</div>
        </div>
"""
        
        # 添加处理记录
        if processing_records:
            content += """
    <div class="section">
        <div class="section-title">处理记录</div>
"""
            for record in processing_records:
                # 安全地访问记录字段
                processor = record.get('processor', '') if hasattr(record, 'get') else (record['processor'] if 'processor' in record.keys() else '')
                created_at = record.get('created_at', '') if hasattr(record, 'get') else (record['created_at'] if 'created_at' in record.keys() else '')
                department = record.get('department', '未指定') if hasattr(record, 'get') else (record['department'] if 'department' in record.keys() and record['department'] else '未指定')
                assigned_to = record.get('assigned_to', '未指定') if hasattr(record, 'get') else (record['assigned_to'] if 'assigned_to' in record.keys() and record['assigned_to'] else '未指定')
                measure = record.get('measure', '') if hasattr(record, 'get') else (record['measure'] if 'measure' in record.keys() else '')
                
                content += f"""
        <div class="processing">
            <div><strong>{processor}</strong> - {created_at}</div>
            <div>部门: {department}</div>
            <div>指派给: {assigned_to}</div>
            <div>处理措施: {measure}</div>
        </div>
"""
        
        # 添加附件
        if files:
            content += """
    <div class="section">
        <div class="section-title">附件文件</div>
"""
            for file in files:
                content += f"""
        <div class="file">
            <div>{file.get('file_name', '')}</div>
            <div>大小: {file.get('file_size', 0)} bytes</div>
            <div>类型: {file.get('file_type', '')}</div>
        </div>
"""
        
        content += """
</body>
</html>
"""
        
        return content
    
    def get_download_link(self, file_path: str, link_text: str) -> str:
        """
        生成文件下载链接
        
        Args:
            file_path: 文件路径
            link_text: 链接文本
            
        Returns:
            HTML下载链接
        """
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            
            b64 = base64.b64encode(data).decode()
            ext = file_path.split('.')[-1]
            
            if ext == 'xlsx':
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif ext == 'pdf':
                mime_type = 'application/pdf'
            else:
                mime_type = 'application/octet-stream'
            
            return f'<a href="data:{mime_type};base64,{b64}" download="{os.path.basename(file_path)}">{link_text}</a>'
            
        except Exception as e:
            # st.error(f"生成下载链接失败: {str(e)}") # Removed st.error
            return ""
    
    def cleanup_old_exports(self, days: int = 7):
        """
        清理旧的导出文件
        
        Args:
            days: 保留天数
        """
        try:
            import time
            current_time = time.time()
            cutoff_time = current_time - (days * 24 * 60 * 60)
            
            for filename in os.listdir(self.export_dir):
                file_path = os.path.join(self.export_dir, filename)
                if os.path.isfile(file_path):
                    if os.path.getmtime(file_path) < cutoff_time:
                        os.remove(file_path)
                        # print(f"已删除旧文件: {filename}") # Removed print
                        
        except Exception as e:
            # print(f"清理旧文件失败: {str(e)}") # Removed print
            pass

# 创建全局实例
# 使用简单的单例模式
_export_manager_instance = None

def get_export_manager():
    global _export_manager_instance
    if _export_manager_instance is None:
        _export_manager_instance = ExportManager()
    return _export_manager_instance

export_manager = get_export_manager() 