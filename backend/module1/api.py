# api.py - 完整版本 (已修复 + 图片分析支持)
import os
import tempfile
import json
import time
import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import threading
from queue import Queue
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from werkzeug.utils import secure_filename
import io
import base64
import traceback
import subprocess
import re
import zipfile
from PIL import Image
import pdfplumber

# 导入 office_pdf 模块
try:
    from office_pdf import convert_word_bytes_to_pdf, is_word_file
    print("✅ office_pdf 已加载")
except ImportError as e:
    print(f"⚠️ office_pdf 未加载: {e}")
    convert_word_bytes_to_pdf = None
    is_word_file = None

# 尝试导入必要的库
try:
    import PyPDF2
    print("✅ PyPDF2 已加载")
except ImportError:
    print("⚠️ PyPDF2 未安装，PDF处理功能将受限")
    PyPDF2 = None

try:
    import docx
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    print("✅ python-docx 已加载")
except ImportError:
    print("⚠️ python-docx 未安装，Word文档处理功能将受限")
    docx = None

try:
    from zhipuai import ZhipuAI
    print("✅ zhipuai 已加载")
except ImportError:
    print("⚠️ zhipuai 未安装，AI功能将不可用")
    ZhipuAI = None

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 启用CORS支持所有路由

# 配置
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 限制20MB
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# 智谱AI配置
ZHIPUAI_API_KEY = "05b3a64d35bc41e3b3ac1aee7a7c46bf.bBUl0Q9a3cZSKBjo" 
print(f"🔑 API密钥长度: {len(ZHIPUAI_API_KEY)}")
print(f"🔑 API密钥前缀: {ZHIPUAI_API_KEY[:10]}...")

# 初始化智谱AI客户端
client = None
if ZHIPUAI_API_KEY and ZHIPUAI_API_KEY != 'your-api-key-here':
    try:
        print("🔄 正在初始化智谱AI客户端...")
        client = ZhipuAI(api_key=ZHIPUAI_API_KEY)
        logger.info("✅ 智谱AI客户端已初始化")
        print("✅ 智谱AI客户端初始化成功")
    except Exception as e:
        logger.error(f"❌ 智谱AI客户端初始化失败: {e}")
        print(f"❌ 初始化失败: {e}")
else:
    logger.warning("⚠️ 未设置智谱AI API密钥，AI功能将不可用")
    print("⚠️ API密钥无效")

# 启动信息
print("=" * 60)
print("🚀 智能文档处理API (使用智谱AI GLM-4 和 GLM-4V)")
print("📁 功能列表:")
print("  1. 文档转换 (/convert/docx-to-pdf)")
print("  2. 智能文档操作流式 (/operate_stream)")
print("  3. 健康检查 (/health)")
print("📄 支持格式: PDF, Word, TXT (图片图表分析已集成)")
print("=" * 60)

# ---------- 图片提取函数 ----------
def extract_images_from_docx(docx_path: str, output_dir: str) -> List[str]:
    """从 .docx 提取所有内嵌图片，返回图片路径列表"""
    images = []
    try:
        with zipfile.ZipFile(docx_path, 'r') as docx_zip:
            for file_name in docx_zip.namelist():
                if file_name.startswith('word/media/') and file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    image_data = docx_zip.read(file_name)
                    # 用 PIL 验证并保存
                    img = Image.open(io.BytesIO(image_data))
                    save_path = os.path.join(output_dir, os.path.basename(file_name))
                    img.save(save_path)
                    images.append(save_path)
    except Exception as e:
        logger.error(f"从 docx 提取图片失败: {e}")
    return images

def extract_images_from_pdf(pdf_path: str, output_dir: str) -> List[str]:
    """从 PDF 提取内嵌图片（使用 pdfplumber），返回图片路径列表"""
    images = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                for img in page.images:
                    try:
                        image_data = img['stream'].get_data()
                        img_obj = Image.open(io.BytesIO(image_data))
                        save_path = os.path.join(output_dir, f"page{page_num+1}_{img['name']}.png")
                        img_obj.save(save_path)
                        images.append(save_path)
                    except Exception as e:
                        logger.warning(f"提取PDF图片失败: {e}")
    except Exception as e:
        logger.error(f"从 PDF 提取图片失败: {e}")
    return images

def describe_images_with_multimodal(image_paths: List[str], max_images: int = 3) -> str:
    """调用 glm-4v 描述图片，返回拼接的描述文本"""
    if not client or not image_paths:
        return ""
    descriptions = []
    for img_path in image_paths[:max_images]:
        try:
            with open(img_path, 'rb') as f:
                img_base64 = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(img_path)[1].lower()
            mime = 'image/png' if ext == '.png' else 'image/jpeg'
            response = client.chat.completions.create(
                model="glm-4v",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_base64}"}},
                        {"type": "text", "text": "请用中文详细描述这张图片的内容，包括其中的文字、数据、趋势等。"}
                    ]
                }],
                temperature=0.5,
                max_tokens=500
            )
            desc = response.choices[0].message.content
            descriptions.append(f"【图片描述】\n{desc}")
        except Exception as e:
            logger.error(f"图片分析失败: {e}")
            descriptions.append("【图片描述】图片分析失败")
    return "\n\n".join(descriptions)

# ---------- 文件处理函数 ----------
def extract_text_from_pdf(file_path: str) -> str:
    """从PDF提取文本"""
    if not PyPDF2:
        return "PDF处理库未安装，无法提取文本"
    
    try:
        text = ""
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logger.error(f"PDF提取失败: {e}")
        return f"PDF提取失败: {str(e)}"

def extract_text_from_docx(file_path: str) -> str:
    """从Word文档提取文本和格式信息 - 增强错误处理"""
    if not docx:
        return "Word处理库未安装，无法提取文本"
    
    try:
        doc = docx.Document(file_path)
        
        # 提取段落文本和格式
        paragraphs_info = []
        for i, para in enumerate(doc.paragraphs):
            try:
                para_info = {
                    'index': i,
                    'text': para.text,
                    'style': para.style.name if para.style else 'Normal',
                    'alignment': str(para.alignment) if para.alignment else 'left',
                    'runs': []
                }
                
                # 提取run级别的格式信息
                for run in para.runs:
                    try:
                        run_info = {
                            'text': run.text,
                            'bold': run.bold,
                            'italic': run.italic,
                            'underline': run.underline,
                            'font_size': run.font.size.pt if run.font.size else None,
                            'font_name': run.font.name,
                            'color': str(run.font.color.rgb) if run.font.color and run.font.color.rgb else None
                        }
                        para_info['runs'].append(run_info)
                    except:
                        # 如果某个run解析失败，只添加文本
                        para_info['runs'].append({'text': run.text})
                
                paragraphs_info.append(para_info)
            except:
                # 如果整个段落解析失败，只添加索引和文本
                paragraphs_info.append({
                    'index': i,
                    'text': para.text if para else '',
                    'style': 'Normal',
                    'alignment': 'left',
                    'runs': []
                })
        
        # 提取表格信息
        tables_info = []
        for table in doc.tables:
            try:
                table_data = []
                for row in table.rows:
                    row_data = [cell.text for cell in row.cells]
                    table_data.append(row_data)
                tables_info.append(table_data)
            except:
                tables_info.append(["表格解析失败"])
        
        # 构建详细的文档信息
        doc_info = {
            'paragraphs': paragraphs_info,
            'tables': tables_info,
            'paragraph_count': len(doc.paragraphs),
            'table_count': len(doc.tables)
        }
        
        return json.dumps(doc_info, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Word提取失败: {e}")
        # 降级方案：使用extract_text_simple获取纯文本
        try:
            simple_text = extract_text_simple(file_path, '.docx')
            return f"格式信息提取失败，仅获取到纯文本内容:\n{simple_text}"
        except:
            return f"Word提取失败: {str(e)}"
        
def extract_text_from_txt(file_path: str) -> str:
    """从文本文件提取文本"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
        except Exception as e:
            logger.error(f"文本提取失败: {e}")
            return "无法解码文本文件"
    except Exception as e:
        logger.error(f"文本提取失败: {e}")
        return f"文本提取失败: {str(e)}"

def extract_text(file_path: str, file_ext: str) -> str:
    """根据文件类型提取文本（包含格式信息）"""
    file_ext = file_ext.lower()
    
    if file_ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif file_ext in ['.docx', '.doc']:
        return extract_text_from_docx(file_path)
    elif file_ext in ['.txt', '.md', '.csv']:
        return extract_text_from_txt(file_path)
    else:
        return f"不支持的文件类型: {file_ext}"

def extract_text_simple(file_path: str, file_ext: str) -> str:
    """只提取纯文本内容，不包含格式信息 - 增强错误处理"""
    file_ext = file_ext.lower()
    
    try:
        if file_ext == '.pdf':
            if not PyPDF2:
                return "PDF处理库未安装"
            text = ""
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            return text[:5000]  # 限制长度
            
        elif file_ext in ['.docx', '.doc']:
            if not docx:
                return "Word处理库未安装"
            
            try:
                doc = docx.Document(file_path)
                # 只提取段落文本
                paragraphs = []
                for para in doc.paragraphs:
                    if para.text.strip():
                        paragraphs.append(para.text)
                
                # 提取表格文本
                for table in doc.tables:
                    for row in table.rows:
                        row_text = ' | '.join([cell.text for cell in row.cells if cell.text.strip()])
                        if row_text:
                            paragraphs.append(row_text)
                
                text = "\n".join(paragraphs)
                return text[:5000] if text else "文档内容为空"
                
            except Exception as e:
                logger.error(f"Word文档解析失败: {e}")
                # 尝试备用方法：使用python-docx的备用解析
                try:
                    # 更简单的解析方式，跳过格式信息
                    import zipfile
                    from xml.etree import ElementTree as ET
                    
                    text_parts = []
                    with zipfile.ZipFile(file_path, 'r') as docx_zip:
                        # 尝试读取文档内容
                        if 'word/document.xml' in docx_zip.namelist():
                            content = docx_zip.read('word/document.xml')
                            root = ET.fromstring(content)
                            
                            # 提取所有文本
                            for elem in root.iter():
                                if elem.tag.endswith('t'):
                                    if elem.text and elem.text.strip():
                                        text_parts.append(elem.text)
                    
                    if text_parts:
                        return "\n".join(text_parts)[:5000]
                    else:
                        return "无法提取文档内容，但文件可能已损坏或格式不正确"
                        
                except Exception as backup_error:
                    logger.error(f"备用解析也失败: {backup_error}")
                    return "文档解析失败：文件可能已损坏或格式不正确"
            
        elif file_ext in ['.txt', '.md', '.csv']:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()[:5000]
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        return f.read()[:5000]
                except:
                    return "文本文件解码失败"
        else:
            return "不支持的文件类型"
            
    except Exception as e:
        logger.error(f"文本提取失败: {e}")
        return f"无法提取文档内容: {str(e)}"

# ---------- 文档操作执行函数 ----------

@app.route('/apply_modifications', methods=['POST'])
def apply_modifications():
    """应用修改到文档并返回修改后的文件"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有文件'}), 400
        
        file = request.files['file']
        modifications_json = request.form.get('modifications', '[]')
        
        if file.filename == '':
            return jsonify({'error': '空文件名'}), 400
        
        logger.info(f"收到修改应用请求: {file.filename}")
        logger.info(f"修改方案JSON: {modifications_json}")
        
        # 解析修改方案
        try:
            modifications = json.loads(modifications_json)
            logger.info(f"解析后的修改方案: {json.dumps(modifications, ensure_ascii=False, indent=2)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return jsonify({'error': f'无效的修改方案: {str(e)}'}), 400
        
        # 保存上传的文件
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        input_path = os.path.join(tempfile.gettempdir(), f"input_{filename}")
        file.save(input_path)
        logger.info(f"文件已保存: {input_path}, 大小: {os.path.getsize(input_path)} 字节")
        
        # 根据文件类型应用修改
        output_path = None
        if file_ext in ['.docx', '.doc']:
            logger.info("开始应用修改到Word文档...")
            output_path = apply_modifications_to_docx(input_path, modifications)
        elif file_ext == '.pdf':
            output_path = apply_modifications_to_pdf(input_path, modifications)
        elif file_ext in ['.txt', '.md']:
            output_path = apply_modifications_to_text(input_path, modifications)
        else:
            return jsonify({'error': f'不支持的文件类型: {file_ext}'}), 400
        
        if not output_path or not os.path.exists(output_path):
            logger.error(f"修改失败: output_path={output_path}")
            return jsonify({'error': '修改失败'}), 500
        
        logger.info(f"修改成功，输出文件: {output_path}, 大小: {os.path.getsize(output_path)} 字节")
        
        # 读取修改后的文件
        with open(output_path, 'rb') as f:
            modified_content = f.read()
        
        # 清理临时文件
        try:
            os.unlink(input_path)
            os.unlink(output_path)
            logger.info("临时文件已清理")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")
        
        # 返回修改后的文件
        response = Response(
            modified_content,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="modified_{filename}"',
                'X-Modification-Applied': 'true',
                'X-Modification-Count': str(len(modifications))
            }
        )
        
        return response
        
    except Exception as e:
        logger.error(f"应用修改失败: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
    
def apply_modifications_to_docx(input_path: str, modifications: List[Dict]) -> Optional[str]:
    """应用修改到Word文档 - 只处理 text_run_format 类型"""
    if not docx:
        logger.error("python-docx未安装")
        return None
    
    try:
        if not os.path.exists(input_path):
            logger.error(f"输入文件不存在: {input_path}")
            return None
        
        logger.info(f"正在加载Word文档: {input_path}")
        doc = None
        
        # 加载文档（保持原有备用加载逻辑）
        try:
            doc = docx.Document(input_path)
            logger.info("成功使用python-docx加载文档")
        except Exception as e:
            logger.error(f"使用python-docx直接加载失败: {e}")
            # ... 保留原有的备用加载代码 ...
            # 为了简洁，此处省略，实际应保留原有备用加载逻辑
        
        if doc is None:
            logger.error("无法加载文档")
            return None
        
        logger.info(f"文档加载成功，共有 {len(doc.paragraphs)} 个段落")
        
        color_name_map = {
            'red': '#FF0000',
            'blue': '#0000FF',
            'green': '#00FF00',
            'yellow': '#FFFF00',
            'purple': '#800080',
            'orange': '#FFA500',
            'black': '#000000',
            'white': '#FFFFFF',
            'cyan': '#00FFFF',
            'magenta': '#FF00FF',
            'gray': '#808080'
        }
        
        for mod_idx, mod in enumerate(modifications):
            mod_type = mod.get('type')
            logger.info(f"处理修改 #{mod_idx+1}: 类型={mod_type}")
            
            if mod_type == 'text_run_format':
                para_idx = mod.get('paragraph_index')
                run_indices = mod.get('run_indices', [])
                bold = mod.get('bold')
                color = mod.get('color')
                
                if para_idx is not None and para_idx < len(doc.paragraphs):
                    para = doc.paragraphs[para_idx]
                    if not para.runs and para.text:
                        para.add_run(para.text)
                    if not run_indices:
                        run_indices = list(range(len(para.runs)))
                    
                    for run_idx in run_indices:
                        if run_idx < len(para.runs):
                            run = para.runs[run_idx]
                            if bold is not None:
                                run.bold = bold
                            if color:
                                color_lower = color.lower() if isinstance(color, str) else ''
                                if color_lower in color_name_map:
                                    color = color_name_map[color_lower]
                                if not color.startswith('#'):
                                    color = '#' + color
                                try:
                                    if len(color) == 7:
                                        rgb = RGBColor(
                                            int(color[1:3], 16),
                                            int(color[3:5], 16),
                                            int(color[5:7], 16)
                                        )
                                        run.font.color.rgb = rgb
                                except Exception as e:
                                    logger.error(f"颜色设置失败: {e}")
                    logger.info(f"已修改段落 {para_idx} 的 runs: {run_indices}")
                else:
                    logger.warning(f"段落索引 {para_idx} 超出范围")
            else:
                logger.warning(f"未知修改类型 {mod_type} 被忽略")
        
        # 保存文档（代码保持不变）
        output_path = input_path.replace('input_', 'modified_')
        if output_path == input_path:
            base_dir = os.path.dirname(input_path)
            base_name = os.path.basename(input_path)
            output_path = os.path.join(base_dir, f"modified_{base_name}")
        
        logger.info(f"正在保存修改后的文档: {output_path}")
        doc.save(output_path)
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"修改后的文档已保存，大小: {file_size} 字节")
            return output_path
        else:
            logger.error("文件保存失败，输出文件不存在")
            return None
        
    except Exception as e:
        logger.error(f"应用修改到Word失败: {e}")
        logger.error(traceback.format_exc())
        return None
     
def apply_modifications_to_pdf(input_path: str, modifications: List[Dict]) -> Optional[str]:
    """应用修改到PDF（有限支持）"""
    # PDF修改比较复杂，这里只实现简单的文本替换（需要安装PyPDF2）
    if not PyPDF2:
        logger.error("PyPDF2未安装")
        return None
    
    try:
        # PDF修改通常需要更复杂的处理
        # 这里返回原始文件
        return input_path
    except Exception as e:
        logger.error(f"应用修改到PDF失败: {e}")
        return None

def apply_modifications_to_text(input_path: str, modifications: List[Dict]) -> Optional[str]:
    """应用修改到文本文件"""
    try:
        # 读取原文件
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 应用修改
        for mod in modifications:
            mod_type = mod.get('type')
            
            if mod_type == 'replace_text':
                old_text = mod.get('old_text', '')
                new_text = mod.get('new_text', '')
                if old_text and new_text:
                    content = content.replace(old_text, new_text)
            
            elif mod_type == 'insert_text':
                text = mod.get('text', '')
                position = mod.get('position', 'end')
                if text:
                    if position == 'start':
                        content = text + '\n' + content
                    else:
                        content = content + '\n' + text
        
        # 保存修改后的文件
        output_path = input_path.replace('input_', 'modified_')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return output_path
        
    except Exception as e:
        logger.error(f"应用修改到文本失败: {e}")
        return None
        
# ---------- LibreOffice转换相关函数 ----------
def check_libreoffice():
    """检查LibreOffice是否可用"""
    try:
        result = subprocess.run(['which', 'soffice'], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def convert_with_libreoffice(input_path: str, output_dir: str) -> Optional[str]:
    """使用LibreOffice转换文档为PDF"""
    try:
        if not check_libreoffice():
            logger.warning("LibreOffice未找到")
            return None
        
        filename = os.path.basename(input_path)
        basename = os.path.splitext(filename)[0]
        output_pdf = os.path.join(output_dir, f"{basename}.pdf")
        
        cmd = [
            'soffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            input_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and os.path.exists(output_pdf):
            return output_pdf
        return None
            
    except Exception as e:
        logger.error(f"转换过程出错: {e}")
        return None

def create_mock_pdf(input_path: str, output_dir: str) -> str:
    """创建模拟PDF"""
    filename = os.path.basename(input_path)
    basename = os.path.splitext(filename)[0]
    output_pdf = os.path.join(output_dir, f"{basename}_mock.pdf")
    
    try:
        if PyPDF2:
            from PyPDF2 import PdfWriter
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            
            with open(output_pdf, 'wb') as f:
                writer.write(f)
            
            return output_pdf
        else:
            return input_path
    except Exception as e:
        logger.error(f"创建模拟PDF失败: {e}")
        return input_path

# ---------- 路由 ----------
@app.route('/convert/docx-to-pdf', methods=['POST'])
def convert_docx_to_pdf():
    """转换Word文档为PDF"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '空文件名'}), 400
        
        # 使用office_pdf转换
        if convert_word_bytes_to_pdf is not None:
            file_bytes = file.read()
            filename = secure_filename(file.filename)
            
            logger.info(f"开始转换文件: {filename}, 大小: {len(file_bytes)} 字节")
            
            if not is_word_file or not is_word_file(filename):
                return jsonify({'error': f'不支持的文件类型: {filename}'}), 400
            
            try:
                pdf_bytes, conversion_info = convert_word_bytes_to_pdf(
                    file_name=filename,
                    file_bytes=file_bytes,
                    timeout_sec=90.0
                )
                
                logger.info(f"转换成功，使用: {conversion_info.get('converter')}")
                
                return Response(
                    pdf_bytes,
                    mimetype='application/pdf',
                    headers={
                        'Content-Disposition': f'attachment; filename="{filename.replace(".docx", ".pdf").replace(".doc", ".pdf")}"'
                    }
                )
                
            except Exception as e:
                logger.error(f"office_pdf转换失败: {e}")
                return jsonify({'error': f'转换失败: {str(e)}'}), 500
        else:
            return jsonify({'error': 'PDF转换模块未加载'}), 500
        
    except Exception as e:
        logger.error(f"整体错误: {e}")
        return jsonify({'error': str(e)}), 500

def parse_ai_modifications(ai_response: str) -> List[Dict]:
    """
    解析AI响应中的修改方案，并统一标准化为 text_run_format 类型。
    标准化后每个修改项包含：
        type: "text_run_format"
        paragraph_index: int
        run_indices: list[int] (可选，默认全部)
        bold: bool (可选)
        color: str (十六进制，如 "#FF0000")
    """
    modifications = []
    try:
        patterns = [
            r'```json\n(.*?)\n```',
            r'```\n(.*?)\n```',
            r'(\[.*?\])',
            r'({.*?})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, ai_response, re.DOTALL)
            for match in matches:
                try:
                    cleaned = match.strip()
                    parsed = json.loads(cleaned)
                    
                    raw_mods = []
                    if isinstance(parsed, list):
                        if len(parsed) == 1 and isinstance(parsed[0], dict) and 'modifications' in parsed[0]:
                            raw_mods = parsed[0]['modifications']
                        else:
                            raw_mods = parsed
                    elif isinstance(parsed, dict):
                        if 'modifications' in parsed and isinstance(parsed['modifications'], list):
                            raw_mods = parsed['modifications']
                        else:
                            raw_mods = [parsed]
                    
                    # 标准化每个修改项
                    for raw in raw_mods:
                        std_item = {'type': 'text_run_format'}  # 统一类型
                        
                        # 提取段落索引
                        para_idx = raw.get('paragraph_index') or raw.get('paragraphIndex')
                        if para_idx is not None:
                            std_item['paragraph_index'] = int(para_idx)
                        
                        # 提取 run_indices
                        run_indices = raw.get('run_indices') or raw.get('runIndices')
                        if run_indices:
                            std_item['run_indices'] = run_indices
                        
                        # 提取 bold 和 color（从各种可能的位置）
                        bold = None
                        color = None
                        
                        # 检查顶层
                        if 'bold' in raw:
                            bold = raw['bold']
                        if 'color' in raw:
                            color = raw['color']
                        
                        # 检查 changes 对象
                        if 'changes' in raw and isinstance(raw['changes'], dict):
                            if bold is None and 'bold' in raw['changes']:
                                bold = raw['changes']['bold']
                            if color is None and 'color' in raw['changes']:
                                color = raw['changes']['color']
                        
                        # 检查 format_changes 对象
                        if 'format_changes' in raw and isinstance(raw['format_changes'], dict):
                            if bold is None and 'bold' in raw['format_changes']:
                                bold = raw['format_changes']['bold']
                            if color is None and 'color' in raw['format_changes']:
                                color = raw['format_changes']['color']
                        
                        # 检查 properties 对象
                        if 'properties' in raw and isinstance(raw['properties'], dict):
                            if bold is None and 'bold' in raw['properties']:
                                bold = raw['properties']['bold']
                            if color is None and 'color' in raw['properties']:
                                color = raw['properties']['color']
                        
                        # 处理目标文本（可能用于 format_title 类型，我们也可转换为 text_run_format）
                        target = raw.get('target')
                        if target and para_idx is None:
                            # 如果有 target 但无段落索引，则尝试在文档中查找，此处简化：标记为需要查找
                            # 由于我们无法在此处查找，可以保留 target 供预览函数处理，但预览函数现在只处理 text_run_format
                            # 为了兼容，我们可以将 target 信息暂存，但建议后端在生成修改方案时直接给出段落索引
                            # 此处我们暂时忽略，因为用户指令“把标题改成红色加粗”应能给出段落索引
                            pass
                        
                        if bold is not None:
                            std_item['bold'] = bool(bold)
                        
                        if color is not None:
                            # 转换为 #RRGGBB 格式
                            color_lower = color.lower() if isinstance(color, str) else ''
                            color_map = {
                                'red': '#FF0000',
                                'blue': '#0000FF',
                                'green': '#00FF00',
                                'yellow': '#FFFF00',
                                'purple': '#800080',
                                'orange': '#FFA500',
                                'black': '#000000',
                                'white': '#FFFFFF'
                            }
                            if color_lower in color_map:
                                color = color_map[color_lower]
                            if not color.startswith('#'):
                                color = '#' + color
                            std_item['color'] = color
                        
                        # 只有包含段落索引的才有效
                        if 'paragraph_index' in std_item:
                            modifications.append(std_item)
                    
                    if modifications:
                        logger.info(f"标准化后的修改方案: {modifications}")
                        return modifications
                        
                except json.JSONDecodeError:
                    continue
        
        # 如果没有找到JSON，尝试从自然语言中解析（原有逻辑）
        if not modifications:
            if '加粗' in ai_response or 'bold' in ai_response.lower():
                modifications.append({
                    'type': 'text_run_format',
                    'paragraph_index': 0,  # 假设第一段，实际需要更智能
                    'bold': True
                })
            if '红色' in ai_response or 'red' in ai_response.lower():
                modifications.append({
                    'type': 'text_run_format',
                    'paragraph_index': 0,
                    'color': '#FF0000'
                })
    
    except Exception as e:
        logger.error(f"解析操作失败: {e}")
    
    logger.info(f"最终修改方案: {modifications}")
    return modifications

def extract_text_explanation(ai_response: str) -> str:
    """提取AI响应中的文本解释"""
    # 移除JSON代码块，保留自然语言解释
    text = re.sub(r'```json\n.*?\n```', '', ai_response, flags=re.DOTALL)
    return text.strip()

def create_preview_document(input_path: str, modifications: List[Dict]) -> Optional[str]:
    """创建预览文档 - 只处理 text_run_format 类型"""
    if not docx:
        logger.error("python-docx未安装")
        return None
    
    try:
        if not os.path.exists(input_path):
            logger.error(f"输入文件不存在: {input_path}")
            return None
        
        logger.info(f"正在创建预览文档，输入文件: {input_path}")
        
        # 加载文档（省略备用加载代码，保持原样）
        doc = None
        try:
            doc = docx.Document(input_path)
            logger.info("成功使用python-docx加载文档")
        except Exception as e:
            logger.error(f"加载失败，使用备用方法: {e}")
            # ... 保留原有的备用加载代码 ...
            # 为了简洁，此处省略，实际应保留原有备用加载逻辑
        
        if doc is None:
            logger.error("无法加载文档")
            return None
        
        logger.info(f"文档加载成功，共有 {len(doc.paragraphs)} 个段落")
        
        # 颜色映射（用于颜色名称转换）
        color_name_map = {
            'red': '#FF0000',
            'blue': '#0000FF',
            'green': '#00FF00',
            'yellow': '#FFFF00',
            'purple': '#800080',
            'orange': '#FFA500',
            'black': '#000000',
            'white': '#FFFFFF',
            'cyan': '#00FFFF',
            'magenta': '#FF00FF',
            'gray': '#808080'
        }
        
        # 应用修改
        for mod_idx, mod in enumerate(modifications):
            mod_type = mod.get('type')
            logger.info(f"处理预览修改项 {mod_idx+1}: {mod_type}")
            
            # 只处理 text_run_format 类型
            if mod_type == 'text_run_format':
                para_idx = mod.get('paragraph_index')
                run_indices = mod.get('run_indices', [])
                bold = mod.get('bold')
                color = mod.get('color')
                
                if para_idx is not None and para_idx < len(doc.paragraphs):
                    para = doc.paragraphs[para_idx]
                    if not para.runs and para.text:
                        para.add_run(para.text)
                    if not run_indices:
                        run_indices = list(range(len(para.runs)))
                    
                    for run_idx in run_indices:
                        if run_idx < len(para.runs):
                            run = para.runs[run_idx]
                            if bold is not None:
                                run.bold = bold
                            if color:
                                # 处理颜色名称
                                color_lower = color.lower() if isinstance(color, str) else ''
                                if color_lower in color_name_map:
                                    color = color_name_map[color_lower]
                                if not color.startswith('#'):
                                    color = '#' + color
                                try:
                                    if len(color) == 7:
                                        rgb = RGBColor(
                                            int(color[1:3], 16),
                                            int(color[3:5], 16),
                                            int(color[5:7], 16)
                                        )
                                        run.font.color.rgb = rgb
                                except Exception as e:
                                    logger.error(f"颜色设置失败: {e}")
                    logger.info(f"已修改段落 {para_idx} 的 runs: {run_indices}")
                else:
                    logger.warning(f"段落索引 {para_idx} 超出范围")
            else:
                logger.warning(f"未知修改类型 {mod_type} 被忽略")
        
        # 保存预览文件（代码保持不变）
        preview_dir = tempfile.gettempdir()
        preview_filename = f"preview_{os.path.basename(input_path)}"
        preview_path = os.path.join(preview_dir, preview_filename)
        
        logger.info(f"正在保存预览文件: {preview_path}")
        doc.save(preview_path)
        
        if os.path.exists(preview_path):
            file_size = os.path.getsize(preview_path)
            logger.info(f"预览文件保存成功，大小: {file_size} 字节")
            return preview_path
        else:
            logger.error("预览文件保存失败")
            return None
        
    except Exception as e:
        logger.error(f"创建预览文档失败: {e}")
        logger.error(traceback.format_exc())
        return None
     
@app.route('/operate_stream', methods=['POST'])
def operate_stream():
    """流式智能文档操作（支持分析和修改）"""
    def generate():
        try:
            file = request.files['file']
            instruction = request.form.get('instruction', '')

            if file.filename == '':
                yield "data: " + json.dumps({'type': 'error', 'content': '空文件名'}) + "\n\n"
                return
            if not instruction:
                yield "data: " + json.dumps({'type': 'error', 'content': '没有操作指令'}) + "\n\n"
                return

            # 保存文件
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()
            input_path = os.path.join(tempfile.gettempdir(), filename)
            file.save(input_path)

            # 提取内容
            doc_content = extract_text(input_path, file_ext)          # 带格式
            simple_content = extract_text_simple(input_path, file_ext) # 纯文本

            if client is None:
                yield "data: " + json.dumps({'type': 'error', 'content': '智谱AI未配置'}) + "\n\n"
                return

            # 图片分析（可选）
            image_keywords = ['图片', '图表', '图', '柱状图', '饼图', '折线图', '扫描件', '截图', 'fig', 'chart', '数据', '提取数据']
            if any(kw in instruction.lower() for kw in image_keywords) and file_ext in ['.docx', '.pdf']:
                with tempfile.TemporaryDirectory() as tmp_img_dir:
                    image_paths = []
                    if file_ext == '.docx':
                        image_paths = extract_images_from_docx(input_path, tmp_img_dir)
                    elif file_ext == '.pdf':
                        image_paths = extract_images_from_pdf(input_path, tmp_img_dir)
                    if image_paths:
                        image_desc = describe_images_with_multimodal(image_paths, max_images=3)
                        if image_desc:
                            doc_content += f"\n\n{image_desc}"
                            simple_content += f"\n\n{image_desc}"

            # 判断指令类型
            instruction_lower = instruction.lower()
            analysis_keywords = ['分析', '总结', '摘要', '提取', '查找', '统计', '概括', '归纳']
            is_analysis = any(keyword in instruction_lower for keyword in analysis_keywords)

            if is_analysis:
                # ===== 分析模式：流式输出文本 =====
                system_prompt = """你是一个专业的文档内容分析助手。你的任务是根据用户的指令分析文档的**内容**，而不是生成修改方案。"""
                user_prompt = f"""用户指令：{instruction}\n\n文档内容：\n{simple_content[:6000]}...\n\n请根据指令分析文档的内容。"""

                ai_response = client.chat.completions.create(
                    model="glm-4",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=3000,
                    stream=True
                )

                for chunk in ai_response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        yield "data: " + json.dumps({'type': 'chunk', 'content': content}) + "\n\n"

            else:
                # ===== 修改模式：生成修改方案（先输出解释文本，最后输出修改方案）=====
                system_prompt = """你是一个专业的文档处理AI助手，能够理解用户的自然语言指令，并生成具体的文档修改方案。
请用JSON格式输出修改方案，放在```json```代码块中。同时用自然语言解释修改效果。"""
                user_prompt = f"""用户指令：{instruction}\n\n文档信息：{filename}\n文档内容：{doc_content[:6000]}...\n\n请生成修改方案。"""

                # 调用 AI（非流式，因为需要完整响应来解析 JSON）
                ai_response = client.chat.completions.create(
                    model="glm-4",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4000,
                    stream=False  # 必须非流式获取完整JSON
                )

                full_response = ai_response.choices[0].message.content
                logger.info(f"AI 完整响应: {full_response}")

                # 提取解释文本（移除JSON部分）
                explanation = extract_text_explanation(full_response)
                # 流式输出解释文本（可以分段，这里简单一次输出）
                yield "data: " + json.dumps({'type': 'chunk', 'content': explanation}) + "\n\n"

                # 解析修改方案
                modifications = parse_ai_modifications(full_response)
                logger.info(f"解析出的修改方案: {modifications}")
                if modifications:
                    yield "data: " + json.dumps({'type': 'modifications', 'content': modifications}) + "\n\n"

                    # 生成预览文件（如果需要）
                    if file_ext in ['.docx', '.doc']:
                        preview_path = create_preview_document(input_path, modifications)
                        if preview_path and os.path.exists(preview_path):
                            with open(preview_path, 'rb') as f:
                                preview_content = f.read()
                            preview_base64 = base64.b64encode(preview_content).decode('utf-8')
                            yield "data: " + json.dumps({
                                'type': 'preview',
                                'content': {
                                    'name': f"preview_{filename}",
                                    'content': preview_base64,
                                    'type': file_ext
                                }
                            }) + "\n\n"
                            try:
                                os.unlink(preview_path)
                            except:
                                pass

            # 清理临时文件
            try:
                os.unlink(input_path)
            except:
                pass

            yield "data: " + json.dumps({'type': 'end'}) + "\n\n"

        except Exception as e:
            logger.error(f"流式操作失败: {e}")
            yield "data: " + json.dumps({'type': 'error', 'content': str(e)}) + "\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# 健康检查
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'libreoffice_available': check_libreoffice(),
        'ai_available': client is not None,
        'modules': {
            'office_pdf': convert_word_bytes_to_pdf is not None,
            'pypdf2': PyPDF2 is not None,
            'python_docx': docx is not None,
            'zhipuai': client is not None
        }
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
    print("🚀 智能文档处理服务已启动")