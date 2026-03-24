import React, { useState, useRef, useCallback, useMemo } from 'react';
import { 
  Bot, MessageSquare, Send, Paperclip, 
  FileText, X, CheckCircle, Plus, Palette, Loader,
  FileUp, Brain, Download, Eye,
  ChevronLeft, ChevronRight, Diff, Split,
  Maximize2, Minimize2, Clock, AlertCircle, Settings,
  ZoomIn, ZoomOut, RotateCw, Layers, Zap, ScanLine,
  Trash2, UploadCloud, File, ChevronRight as ChevronRightIcon,
  Plus as PlusIcon, CheckCircle2, Grid, List, Sparkles
} from 'lucide-react';
import * as XLSX from 'xlsx';
import { Image } from 'lucide-react';

// ---------- 类型定义 ----------
interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  fileIds?: string[];
  timestamp: Date;
}

interface FileInfo {
  id: string;
  name: string;
  size: number;
  type: string;
  content?: string;
  uploadTime: Date;
  status: 'uploading' | 'ready' | 'error' | 'processing' | 'completed' | 'converting';
  progress?: number;
  file?: File;
  preview?: string;
  result?: string;
  error?: string;
  originalFile?: File; // 保存原始文件用于操作
}

interface Modification {
  type: string;
  target?: string;
  changes?: any;
  old_text?: string;
  new_text?: string;
  rows?: number;
  cols?: number;
  position?: string;
  preview?: {
    before?: string;
    after?: string;
    description?: string;
  };
}

interface OperationResult {
  success: boolean;
  instruction: string;
  ai_explanation: string;
  modifications: Modification[];
  file_info: {
    name: string;
    type: string;
    size: number;
  };
  preview?: {
    name: string;
    content: string;
    type: string;
  };
}

interface StyleAnalysisResponse {
  success: boolean;
  template_info: {
    filename: string;
    paragraphs: number;
    tables: number;
    styles: string[];
    features: {
      fonts: string[];
      font_sizes: string[];
      colors: string[];
      alignments: string[];
      headings: any[];
    };
  };
  target_info: {
    filename: string;
    paragraphs: number;
    tables: number;
    styles: string[];
  };
}

interface StylePreviewResponse {
  success: boolean;
  original_preview: string;
  modified_preview: string;
  comparison: {
    summary: string;
    changes: string[];
  };
  file_type: string;
  style_applied: string;
  modified_file?: {
    name: string;
    content: string;
  };
}

// 样式克隆步骤类型
type StyleStep = 'upload' | 'analyze' | 'preview' | 'complete';
// 预览视图模式
type ViewMode = 'split' | 'single' | 'diff';
// 布局模式
type LayoutMode = 'default' | 'compact' | 'expanded';

// 辅助函数
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

const fileExt = (name: string) => name.split('.').pop()?.toLowerCase() ?? '';

const toPageNumber = (bbox: number[]): number | null => {
  if (bbox.length !== 5) return null;
  const page = Number(bbox[0]);
  if (!Number.isFinite(page) || page < 1) return null;
  return Math.round(page);
};

const toPercentBox = (bbox: number[]) => {
  if (bbox.length !== 5) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }

  const [, x, y, w, h] = bbox;
  const maxVal = Math.max(x + w, y + h);

  if (maxVal <= 1.5) {
    return { x: x * 100, y: y * 100, w: w * 100, h: h * 100 };
  }

  if (maxVal <= 100) {
    return { x, y, w, h };
  }

  return { x: (x / 595) * 100, y: (y / 842) * 100, w: (w / 595) * 100, h: (h / 842) * 100 };
};

// ---------- 主组件 ----------
export const DocInteractionWorkbench: React.FC = () => {
  // 文档存储
  const [files, setFiles] = useState<Record<string, FileInfo>>({});
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  
  // 聊天状态
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'assistant',
      content: `👋 你好！我是文档智能助手

**我可以帮你：**
• 📊 **文档分析** - 风险分析、合规检查、趋势分析、信息提取
• 📝 **文档操作** - 格式化标题、调整段落、插入表格、计算数值
• 🎨 **样式克隆** - 复制模板样式到目标文档

**使用方式：**
1. 上传一个或多个文档（支持 PDF、Word、TXT）
2. 输入你的指令，例如：
   - "分析这些合同的风险点"
   - "提取所有金额和日期"
   - "把标题改成红色加粗"`,
      timestamp: new Date()
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('default');
  
  // 预览控制
  const [scale, setScale] = useState(0.9);
  const [rotation, setRotation] = useState(0);
  const [pdfPage, setPdfPage] = useState(1);
  
  // 修改预览相关状态
  const [pendingModifications, setPendingModifications] = useState<OperationResult | null>(null);
  const [previewFile, setPreviewFile] = useState<{name: string, content: string, type: string} | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [targetFileForModification, setTargetFileForModification] = useState<FileInfo | null>(null);
  
  // PDF预览相关状态
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [showPdfPreview, setShowPdfPreview] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [showPreviewPanel, setShowPreviewPanel] = useState(false);

  // 样式克隆状态
  const [styleState, setStyleState] = useState<{
    isOpen: boolean;
    step: StyleStep;
    templateFile: File | null;
    targetFile: File | null;
    analysis: StyleAnalysisResponse | null;
    preview: StylePreviewResponse | null;
    styleChoice: string;
    isProcessing: boolean;
    error: string;
    viewMode: ViewMode;
    zoomLevel: number;
  }>({
    isOpen: false,
    step: 'upload',
    templateFile: null,
    targetFile: null,
    analysis: null,
    preview: null,
    styleChoice: 'all',
    isProcessing: false,
    error: '',
    viewMode: 'split',
    zoomLevel: 100
  });

  // 统一API地址
  const UNIFIED_API_URL = 'http://localhost:5000';

  // 计算属性
  const fileList = useMemo(() => Object.values(files), [files]);
  const selectedFile = useMemo(
    () => selectedFileId ? files[selectedFileId] : null,
    [files, selectedFileId]
  );
  
  const activeFileExt = selectedFile ? fileExt(selectedFile.name) : '';
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string>('');

  // 预览URL管理
  React.useEffect(() => {
    if (!selectedFile?.preview) {
      console.log('没有预览URL');
      setPreviewUrl(null);
      return;
    }
    
    console.log('设置预览URL:', {
      url: selectedFile.preview,
      type: selectedFile.type,
      name: selectedFile.name,
      status: selectedFile.status
    });
    
    setPreviewUrl(selectedFile.preview);
    
    // 对于blob协议，不需要fetch测试，直接认为可用
    if (selectedFile.preview.startsWith('blob:')) {
      console.log('使用blob协议，跳过fetch测试');
    }
  }, [selectedFile]);

  // 文本预览 - 只处理纯文本文件
  React.useEffect(() => {
    let cancelled = false;
    // 只处理纯文本文件，不处理 Excel
    if (!selectedFile?.file || !['txt', 'md', 'csv'].includes(activeFileExt)) {
      setPreviewText('');
      return;
    }
    selectedFile.file.text().then((text) => {
      if (cancelled) return;
      const maxChars = 12000;
      setPreviewText(text.length > maxChars ? `${text.slice(0, maxChars)}\n\n... [truncated]` : text);
    }).catch(err => {
      console.error('读取文本文件失败:', err);
      setPreviewText('文件读取失败');
    });
    return () => { cancelled = true; };
  }, [selectedFile, activeFileExt]);

  // 自动滚动
  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 组件卸载时中止请求
  React.useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // ---------- Word转PDF转换函数 ----------
  const convertWordToPdf = async (file: File): Promise<{ pdfBlob: Blob; pdfFile: File } | null> => {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      console.log(`开始转换Word文件: ${file.name}`);
      const response = await fetch(`${UNIFIED_API_URL}/convert/docx-to-pdf`, {
        method: 'POST',
        body: formData
      });
      
      // 先检查响应状态
      if (!response.ok) {
        const errorText = await response.text();
        console.error('服务器返回错误:', response.status, errorText);
        throw new Error(`转换失败: ${response.status} - ${errorText}`);
      }
      
      // 检查响应内容类型
      const contentType = response.headers.get('content-type');
      console.log('响应内容类型:', contentType);
      
      // 如果不是PDF，可能返回了错误信息
      if (!contentType?.includes('application/pdf')) {
        const errorText = await response.text();
        console.error('返回的不是PDF文件:', errorText);
        throw new Error(`服务器返回了错误: ${errorText}`);
      }
      
      const pdfBlob = await response.blob();
      
      // 检查blob是否有效
      if (pdfBlob.size === 0) {
        throw new Error('转换后的PDF文件为空');
      }
      
      console.log('PDF Blob大小:', pdfBlob.size, 'bytes');
      
      const pdfFileName = file.name.replace(/\.[^/.]+$/, '') + '.pdf';
      
      // 修复：使用Blob和File的兼容方式创建File对象
      let pdfFile: File;
      try {
        pdfFile = new File([pdfBlob], pdfFileName, { type: 'application/pdf' });
      } catch (e) {
        console.warn('File constructor not available, using fallback method');
        pdfFile = pdfBlob as File;
        Object.defineProperties(pdfFile, {
          name: { value: pdfFileName, writable: false },
          lastModified: { value: Date.now(), writable: false }
        });
      }
      
      console.log(`转换成功: ${pdfFileName}`);
      return { pdfBlob, pdfFile };
    } catch (error) {
      console.error('Word转PDF失败:', error);
      alert(`转换失败: ${error instanceof Error ? error.message : '未知错误'}`);
      return null;
    }
  };

  // ---------- 文件上传 ----------
  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;

    const newFiles = { ...files };
    const fileIds: string[] = [];

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      
      // 允许所有常见格式
      const allowedExtensions = ['.pdf', '.doc', '.docx', '.txt', '.xlsx', '.md', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'];
      
      if (!allowedExtensions.includes(ext)) {
        alert(`文件 ${file.name} 格式不支持`);
        continue;
      }

      if (file.size > 20 * 1024 * 1024) {
        alert(`文件 ${file.name} 大小超过20MB`);
        continue;
      }

      const fileId = Date.now() + Math.random().toString(36).substr(2, 9) + i;
      fileIds.push(fileId);
      
      // 创建预览URL
      let previewUrl = URL.createObjectURL(file);
      
      // 先创建临时文件对象
      newFiles[fileId] = {
        id: fileId,
        name: file.name,
        size: file.size,
        type: file.type,
        uploadTime: new Date(),
        status: ext === '.doc' || ext === '.docx' ? 'converting' : 'ready',
        progress: ext === '.doc' || ext === '.docx' ? 30 : 100,
        file: file,
        preview: previewUrl,
        originalFile: file
      };
    }

    // 先更新UI显示文件列表
    setFiles(newFiles);
    
    // 自动选择第一个文件
    if (fileIds.length > 0 && !selectedFileId) {
      setSelectedFileId(fileIds[0]);
    }

    // 然后对Word文件进行异步转换
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      const fileId = fileIds[i];
      
      if (ext === '.doc' || ext === '.docx') {
        // 执行转换
        const conversionResult = await convertWordToPdf(file);
  
        if (conversionResult) {
          // 转换成功，更新文件信息
          const pdfBlob = conversionResult.pdfBlob;
          const pdfFile = conversionResult.pdfFile;
          const pdfPreviewUrl = URL.createObjectURL(pdfBlob);
          
          // 清理旧的预览URL
          URL.revokeObjectURL(newFiles[fileId].preview);
          
          setFiles(prev => ({
            ...prev,
            [fileId]: {
              ...prev[fileId],
              name: pdfFile.name,
              type: 'application/pdf',
              status: 'ready',
              progress: 100,
              file: pdfFile,
              preview: pdfPreviewUrl,
              originalFile: file // 保留原始文件用于操作
            }
          }));
        } else {
          // 转换失败
          console.error(`文件 ${file.name} 转换失败`);
          
          setFiles(prev => ({
            ...prev,
            [fileId]: {
              ...prev[fileId],
              status: 'error',
              progress: 0,
              error: `转换PDF失败: 服务器返回500错误，请检查后端服务`
            }
          }));
          
          alert(`文件 ${file.name} 转换失败，请检查后端服务是否正常运行`);
        }
      }
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [files, selectedFileId]);

  const removeFile = useCallback((fileId: string) => {
    setFiles(prev => {
      const newFiles = { ...prev };
      delete newFiles[fileId];
      return newFiles;
    });
    
    if (selectedFileId === fileId) {
      setSelectedFileId(null);
    }
  }, [selectedFileId]);

  const clearAllFiles = useCallback(() => {
    if (Object.keys(files).length > 0 && window.confirm('确定要移除所有已上传的文档吗？')) {
      setFiles({});
      setSelectedFileId(null);
      setScale(1);
      setRotation(0);
      setPdfPage(1);
    }
  }, [files]);

  const triggerFileInput = useCallback(() => fileInputRef.current?.click(), []);

  // ---------- API 调用 ----------
  // 应用修改的函数 - 完整实现
  const applyModifications = useCallback(async () => {
    if (!pendingModifications || !targetFileForModification) {
      alert('没有待应用的修改');
      return;
    }
    
    try {
      setIsLoading(true);
      
      // 获取要修改的文件
      const fileToModify = targetFileForModification.originalFile || targetFileForModification.file;
      if (!fileToModify) {
        throw new Error('找不到要修改的文件');
      }
      
      // 准备修改数据
      const formData = new FormData();
      formData.append('file', fileToModify);
      formData.append('modifications', JSON.stringify(pendingModifications.modifications || []));
      
      console.log('正在应用修改:', {
        fileName: fileToModify.name,
        modifications: pendingModifications.modifications
      });
      
      // 调用应用修改的API
      const response = await fetch(`${UNIFIED_API_URL}/apply_modifications`, {
        method: 'POST',
        body: formData
      });
      
      console.log('API响应状态:', response.status);
      console.log('API响应头:', Object.fromEntries(response.headers.entries()));
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('API错误响应:', errorText);
        throw new Error(`应用修改失败: ${response.status} - ${errorText}`);
      }
      
      // 获取修改后的文件
      const modifiedBlob = await response.blob();
      console.log('修改后的文件大小:', modifiedBlob.size, 'bytes');
      
      // 从响应头获取修改信息（注意：这些头可能不存在）
      const modificationApplied = response.headers.get('X-Modification-Applied');
      const modificationCount = response.headers.get('X-Modification-Count') || 
                                (pendingModifications.modifications?.length || 0).toString();
      
      console.log('修改信息:', { modificationApplied, modificationCount });
      
      // 创建修改后的文件对象
      const contentDisposition = response.headers.get('Content-Disposition');
      let fileName = `modified_${targetFileForModification.name}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (match && match[1]) {
          fileName = match[1].replace(/['"]/g, '');
        }
      }
      
      // 创建File对象
      let modifiedFile;
      try {
        modifiedFile = new File([modifiedBlob], fileName, { type: modifiedBlob.type || 'application/octet-stream' });
      } catch (e) {
        console.warn('File constructor not available, using fallback');
        modifiedFile = modifiedBlob as File;
        Object.defineProperties(modifiedFile, {
          name: { value: fileName, writable: false },
          lastModified: { value: Date.now(), writable: false }
        });
      }
      
      // 生成预览URL
      const modifiedPreviewUrl = URL.createObjectURL(modifiedBlob);
      
      // 更新文件列表，添加修改后的文件
      const newFileId = Date.now() + Math.random().toString(36).substr(2, 9);
      
      setFiles(prev => {
        const newFiles = { ...prev };
        
        // 添加修改后的文件
        newFiles[newFileId] = {
          id: newFileId,
          name: fileName,
          size: modifiedBlob.size,
          type: modifiedBlob.type || 'application/octet-stream',
          uploadTime: new Date(),
          status: 'ready',
          progress: 100,
          file: modifiedFile,
          preview: modifiedPreviewUrl,
          originalFile: fileToModify,
          result: `已应用 ${modificationCount} 项修改`
        };
        
        return newFiles;
      });
      
      // 自动选中新文件
      setSelectedFileId(newFileId);
      
      // 添加成功消息
      const successMessage: Message = {
        id: Date.now().toString(),
        type: 'assistant',
        content: `✅ 修改已成功应用！\n\n已生成修改后的文件: ${fileName}\n共应用了 ${modificationCount} 项修改。\n\n注意：由于原文档格式问题，使用备用方法处理，可能只保留了文本内容。`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, successMessage]);
      
      // 关闭预览对话框
      setShowPreview(false);
      setPendingModifications(null);
      setPreviewFile(null);
      setTargetFileForModification(null);
      
      // 清理PDF预览URL
      if (pdfPreviewUrl) {
        URL.revokeObjectURL(pdfPreviewUrl);
        setPdfPreviewUrl(null);
      }
      setShowPdfPreview(false);
      
    } catch (error) {
      console.error('应用修改失败:', error);
      
      // 添加错误消息
      const errorMessage: Message = {
        id: Date.now().toString(),
        type: 'assistant',
        content: `❌ 应用修改失败\n\n${error instanceof Error ? error.message : '未知错误'}\n\n请查看控制台获取详细信息。`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
      
      alert(`应用修改失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setIsLoading(false);
    }
  }, [pendingModifications, targetFileForModification, pdfPreviewUrl]);

  const getStatusIcon = useCallback((status: string) => {
    switch(status) {
      case 'ready':
        return <CheckCircle size={14} className="text-green-500" />;
      case 'converting':
        return <Loader size={14} className="text-yellow-500 animate-spin" />;
      case 'processing':
        return <Loader size={14} className="text-blue-500 animate-spin" />;
      case 'completed':
        return <CheckCircle size={14} className="text-green-500" />;
      case 'error':
        return <AlertCircle size={14} className="text-red-500" />;
      default:
        return <Clock size={14} className="text-slate-400" />;
    }
  }, []);

  const getStatusText = useCallback((status: string) => {
    switch(status) {
      case 'ready':
        return '就绪';
      case 'converting':
        return '转换中';
      case 'processing':
        return '处理中';
      case 'completed':
        return '已完成';
      case 'error':
        return '错误';
      default:
        return '等待';
    }
  }, []);

  const handleKeyPress = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }, [inputText, isLoading, Object.keys(files).length]);

  // Excel预览组件
  const ExcelPreview: React.FC<{ file: FileInfo }> = ({ file }) => {
    const [sheets, setSheets] = useState<{ name: string; data: any[][] }[]>([]);
    const [activeSheet, setActiveSheet] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    React.useEffect(() => {
      const loadExcel = async () => {
        try {
          setLoading(true);
          setError(null);
          
          console.log('ExcelPreview 开始加载文件:', file.name);
          const fileToRead = file.file || file.originalFile;
          if (!fileToRead) {
            throw new Error('文件不存在');
          }

          const buffer = await fileToRead.arrayBuffer();
          const workbook = XLSX.read(buffer, { type: 'array' });
          
          const sheetsData = workbook.SheetNames.map(name => {
            const sheet = workbook.Sheets[name];
            const data = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' }) as any[][];
            return { name, data };
          });
          
          setSheets(sheetsData);
        } catch (err) {
          console.error('Excel加载失败:', err);
          setError(err instanceof Error ? err.message : 'Excel加载失败');
        } finally {
          setLoading(false);
        }
      };

      loadExcel();
    }, [file]);

    if (loading) {
      return (
        <div className="flex flex-col items-center justify-center h-full">
          <Loader size={40} className="animate-spin text-green-500 mb-4" />
          <p className="text-sm text-slate-500">正在加载Excel文件...</p>
        </div>
      );
    }

    if (error) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
          <AlertCircle size={48} className="mx-auto mb-4 text-red-500" />
          <p className="text-sm text-red-500 mb-4">{error}</p>
          <button
            onClick={() => downloadFile(file)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700"
          >
            下载文件
          </button>
        </div>
      );
    }

    return (
      <div className="flex flex-col h-full">
        <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg flex justify-between items-center">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Excel预览</span>
            {sheets.length > 1 && (
              <select
                value={activeSheet}
                onChange={(e) => setActiveSheet(Number(e.target.value))}
                className="text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-2 py-1"
              >
                {sheets.map((sheet, index) => (
                  <option key={sheet.name} value={index}>
                    {sheet.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          <button
            onClick={() => downloadFile(file)}
            className="px-3 py-1.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 flex items-center gap-1"
          >
            <Download size={14} />
            下载文件
          </button>
        </div>
        
        <div className="flex-1 overflow-auto border border-slate-200 dark:border-slate-700 rounded-lg">
          {sheets.length > 0 && sheets[activeSheet] && (
            <table className="w-full border-collapse text-sm">
              <tbody>
                {sheets[activeSheet].data.map((row, rowIndex) => (
                  <tr key={rowIndex} className={rowIndex === 0 ? 'bg-slate-100 dark:bg-slate-700 font-medium' : 'border-t border-slate-200 dark:border-slate-700'}>
                    {Array.from({ length: Math.max(...sheets[activeSheet].data.map(r => r.length), 0) }).map((_, colIndex) => (
                      <td key={colIndex} className="px-3 py-2 border-r border-slate-200 dark:border-slate-700 last:border-r-0">
                        {row[colIndex] !== undefined && row[colIndex] !== null ? String(row[colIndex]) : ''}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        
        <div className="mt-2 text-xs text-slate-400 text-right">
          共 {sheets.length} 个工作表 · 当前: {sheets[activeSheet]?.name}
        </div>
      </div>
    );
  };

  // Markdown预览组件
  const MarkdownPreview: React.FC<{ content: string; fileName: string; onDownload: () => void }> = ({ content, fileName, onDownload }) => {
    return (
      <div className="flex flex-col h-full">
        <div className="mb-4 p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg flex justify-between items-center">
          <span className="text-sm font-medium">Markdown预览</span>
          <button
            onClick={onDownload}
            className="px-3 py-1.5 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 flex items-center gap-1"
          >
            <Download size={14} />
            下载文件
          </button>
        </div>
        <div className="flex-1 overflow-auto prose prose-sm dark:prose-invert max-w-none p-2">
          {content ? (
            <div className="p-2">
              {content.split('\n').map((line, i) => {
                if (line.startsWith('# ')) {
                  return <h1 key={i} className="text-2xl font-bold mt-4 mb-2">{line.slice(2)}</h1>;
                } else if (line.startsWith('## ')) {
                  return <h2 key={i} className="text-xl font-bold mt-3 mb-2">{line.slice(3)}</h2>;
                } else if (line.startsWith('### ')) {
                  return <h3 key={i} className="text-lg font-bold mt-2 mb-1">{line.slice(4)}</h3>;
                } else if (line.startsWith('#### ')) {
                  return <h4 key={i} className="text-base font-bold mt-2 mb-1">{line.slice(5)}</h4>;
                } else if (line.startsWith('**') && line.endsWith('**')) {
                  return <p key={i} className="font-bold">{line.slice(2, -2)}</p>;
                } else if (line.startsWith('*') && line.endsWith('*')) {
                  return <p key={i} className="italic">{line.slice(1, -1)}</p>;
                } else if (line.startsWith('- ')) {
                  return <li key={i} className="ml-4 list-disc">{line.slice(2)}</li>;
                } else if (line.match(/^\d+\. /)) {
                  return <li key={i} className="ml-4 list-decimal">{line.replace(/^\d+\. /, '')}</li>;
                } else if (line.trim() === '') {
                  return <div key={i} className="h-2" />;
                } else {
                  return <p key={i} className="mb-2">{line}</p>;
                }
              })}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <Loader size={30} className="animate-spin text-purple-500" />
            </div>
          )}
        </div>
      </div>
    );
  };
  // ---------- 发送消息 ----------
  const sendMessage = useCallback(async () => {
    if (!inputText.trim() || isLoading) return;
    if (Object.keys(files).length === 0) {
      alert('请先上传文档');
      return;
    }

    // 中止之前的请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // 创建新的 AbortController
    abortControllerRef.current = new AbortController();

    const fileIds: string[] = Object.keys(files);
    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputText,
      fileIds: fileIds,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMessage]);
    setInputText('');
    setIsLoading(true);

    try {
      // 获取当前选中的文件（若没有选中则用第一个）
      let targetFileInfo = selectedFileId ? files[selectedFileId] : Object.values(files)[0];
      if (!targetFileInfo || !targetFileInfo.file) {
        throw new Error('文件对象丢失');
      }

      const fileToUse = targetFileInfo.originalFile || targetFileInfo.file;
      const formData = new FormData();
      formData.append('file', fileToUse);
      formData.append('instruction', inputText);

      // 创建占位消息（流式内容将累加至此）
      const assistantMessageId = (Date.now() + 2).toString();
      setMessages(prev => [
        ...prev,
        {
          id: assistantMessageId,
          type: 'assistant',
          content: '',
          fileIds: [targetFileInfo.id],
          timestamp: new Date()
        }
      ]);

      // 调用流式 API
      const response = await fetch(`${UNIFIED_API_URL}/operate_stream`, {
        method: 'POST',
        body: formData,
        signal: abortControllerRef.current.signal
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`请求失败: ${response.status} - ${errorText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('无法读取响应流');

      let accumulatedContent = '';
      let buffer = '';

      while (true) {
        if (abortControllerRef.current?.signal.aborted) {
          reader.cancel();
          console.log('用户中断了流式请求');
          return;
        }

        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);

              switch (parsed.type) {
                case 'chunk':
                  // 文本片段：累加到消息内容
                  accumulatedContent += parsed.content;
                  setMessages(prev =>
                    prev.map(msg =>
                      msg.id === assistantMessageId
                        ? { ...msg, content: accumulatedContent }
                        : msg
                    )
                  );
                  break;

                case 'modifications':
                  console.log('收到修改方案:', parsed.content);
                  setTargetFileForModification(targetFileInfo);
                  
                  // 提取真实修改项数组
                  let realModifications = Array.isArray(parsed.content) ? parsed.content : [];
                  if (realModifications.length === 1 && realModifications[0].modifications) {
                    realModifications = realModifications[0].modifications;
                  }
                  
                  // 标准化：将 changes/format_changes/properties 中的属性提升到顶层
                  realModifications = realModifications.map(mod => {
                      if (mod.changes && typeof mod.changes === 'object') {
                          mod = { ...mod, ...mod.changes };
                      }
                      if (mod.format_changes && typeof mod.format_changes === 'object') {
                          mod = { ...mod, ...mod.format_changes };
                      }
                      if (mod.properties && typeof mod.properties === 'object') {
                          mod = { ...mod, ...mod.properties };
                      }
                      if (mod.paragraphIndex !== undefined && mod.paragraph_index === undefined) {
                          mod.paragraph_index = mod.paragraphIndex;
                      }
                      return mod;
                  });
                  
                  setPendingModifications({
                    success: true,
                    instruction: inputText,
                    ai_explanation: accumulatedContent,
                    modifications: realModifications,
                    file_info: {
                      name: targetFileInfo.name,
                      type: targetFileInfo.type,
                      size: targetFileInfo.size
                    }
                  });
                  setShowPreview(true);
                  break;

                case 'preview':
                  // 收到预览文件信息
                  setPreviewFile(parsed.content);
                  break;

                case 'error':
                  console.error('流式错误:', parsed.content);
                  throw new Error(parsed.content);

                case 'end':
                  // 处理完成，可以更新文件状态（可选）
                  break;

                default:
                  console.warn('未知消息类型:', parsed.type);
              }
            } catch (e) {
              console.error('解析流数据失败:', e, line);
            }
          }
        }
      }

      // 更新文件状态为已完成
      setFiles(prev => {
        const newFiles = { ...prev };
        for (const fileId of fileIds) {
          if (newFiles[fileId]) {
            newFiles[fileId].status = 'completed';
            newFiles[fileId].progress = 100;
          }
        }
        return newFiles;
      });

    } catch (error) {
      // 处理错误（如果是用户主动中止则不显示错误）
      if (error instanceof Error && error.name === 'AbortError') {
        setMessages(prev => [
          ...prev,
          {
            id: Date.now().toString(),
            type: 'assistant',
            content: '⏹️ 已停止生成',
            timestamp: new Date()
          }
        ]);
        return;
      }

      console.error('处理请求失败:', error);
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          type: 'assistant',
          content: `❌ **处理失败**\n\n${error instanceof Error ? error.message : '未知错误'}\n\n请检查网络连接或稍后重试。`,
          timestamp: new Date()
        }
      ]);

      // 标记文件为错误状态
      setFiles(prev => {
        const newFiles = { ...prev };
        for (const id in newFiles) {
          newFiles[id].status = 'error';
        }
        return newFiles;
      });
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, [inputText, isLoading, files, selectedFileId, UNIFIED_API_URL]);
  // 预览控制函数
  const handleZoomIn = () => setScale((prev) => Math.min(prev + 0.1, 2.5));
  const handleZoomOut = () => setScale((prev) => Math.max(prev - 0.1, 0.5));
  const handleRotate = () => setRotation((prev) => (prev + 90) % 360);
  const handleResetView = () => {
    setScale(1);
    setRotation(0);
  };

  // 样式克隆相关
  const openStyleTransfer = useCallback(() => {
    setStyleState({
      isOpen: true,
      step: 'upload',
      templateFile: null,
      targetFile: null,
      analysis: null,
      preview: null,
      styleChoice: 'all',
      isProcessing: false,
      error: '',
      viewMode: 'split',
      zoomLevel: 100
    });
  }, []);

  const closeStyleTransfer = useCallback(() => {
    setStyleState(prev => ({ ...prev, isOpen: false }));
  }, []);

  const handleTemplateFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setStyleState(prev => ({ ...prev, templateFile: file, error: '' }));
    }
  }, []);

  const handleTargetFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setStyleState(prev => ({ ...prev, targetFile: file, error: '' }));
    }
  }, []);

  const setViewMode = useCallback((mode: ViewMode) => {
    setStyleState(prev => ({ ...prev, viewMode: mode }));
  }, []);

  const zoomIn = useCallback(() => {
    setStyleState(prev => ({ ...prev, zoomLevel: Math.min(prev.zoomLevel + 10, 150) }));
  }, []);

  const zoomOut = useCallback(() => {
    setStyleState(prev => ({ ...prev, zoomLevel: Math.max(prev.zoomLevel - 10, 50) }));
  }, []);

  const highlightDifferences = useCallback((original: string, modified: string) => {
    const originalLines = original.split('\n');
    const modifiedLines = modified.split('\n');
    
    return (
      <div className="space-y-1">
        {modifiedLines.map((line, i) => {
          const originalLine = i < originalLines.length ? originalLines[i] : '';
          const isNew = i >= originalLines.length;
          const isChanged = originalLine !== line && !isNew;
          
          let bgColor = '';
          if (isNew) bgColor = 'bg-green-100 dark:bg-green-900/30';
          else if (isChanged) bgColor = 'bg-yellow-100 dark:bg-yellow-900/30';
          
          return (
            <div key={i} className={`${bgColor} px-2 py-0.5 rounded`}>
              <span className="text-slate-700 dark:text-slate-300">{line}</span>
              {isChanged && (
                <span className="ml-2 text-xs text-yellow-600 dark:text-yellow-400">
                  (原: {originalLine})
                </span>
              )}
            </div>
          );
        })}
      </div>
    );
  }, []);

  // 下载文件
  const downloadFile = useCallback((file: FileInfo) => {
    const fileToDownload = file.originalFile || file.file;
    if (!fileToDownload) return;
    
    try {
      const url = URL.createObjectURL(fileToDownload);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (error) {
      console.error('下载文件失败:', error);
      alert('下载文件失败，请重试');
    }
  }, []);

  // 导出结果
  const exportResults = useCallback(() => {
    if (fileList.length === 0) return;

    const exportData = {
      files: fileList.map(f => ({
        name: f.name,
        size: f.size,
        status: f.status,
        result: f.result,
        uploadTime: f.uploadTime
      })),
      messages: messages
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `doc-interaction-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [fileList, messages]);

  return (
    <div className="absolute inset-0 flex flex-col bg-gradient-to-br from-blue-100/90 via-blue-50/90 to-indigo-100/90 dark:from-blue-950/90 dark:via-slate-950/90 dark:to-indigo-950/90 overflow-hidden backdrop-blur-sm">
      {/* 头部 */}
      <div className="flex items-center justify-between p-4 border-b border-blue-200/40 dark:border-blue-800/40 shrink-0 backdrop-blur-xl bg-white/40 dark:bg-slate-900/40 shadow-lg shadow-blue-500/10">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400">
            <Bot size={20} />
          </div>
          <div>
            <h2 className="font-bold text-slate-900 dark:text-white">文档智能交互工作台</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">智谱AI GLM-4 · 智能文档处理</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              if (selectedFile) {
                setShowPreviewPanel(!showPreviewPanel);
              } else {
                alert('请先选择要预览的文档');
              }
            }}
            className={`p-2 rounded-lg transition-colors ${
              showPreviewPanel 
                ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400' 
                : 'hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
            title="文档预览"
          >
            <Eye size={18} />
          </button>
          <button
            onClick={openStyleTransfer}
            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
          >
            <Palette size={18} className="text-indigo-600" />
          </button>
        </div>
      </div>

      {/* 主要内容区域 - 根据预览状态决定布局 */}
      <div className="flex-1 flex p-4 gap-4 min-h-0 overflow-hidden">
        
        {/* 左侧聊天区 - 根据预览状态调整宽度 */}
        <div className={`flex flex-col backdrop-blur-xl bg-white/60 dark:bg-slate-900/60 rounded-2xl border border-blue-200/40 dark:border-blue-800/40 h-full transition-all duration-300 overflow-hidden shadow-xl shadow-blue-500/10 ${
          showPreviewPanel ? 'w-2/5' : 'w-full max-w-8xl mx-auto'
        }`}>
          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto p-5 space-y-3 min-h-0">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[90%] rounded-2xl px-4 py-4 text-sm backdrop-blur-md ${
                    message.type === 'user'
                      ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg shadow-blue-500/30'
                      : 'bg-white/10 dark:bg-slate-800/95 border border-blue-200/40 dark:border-blue-700/50 shadow-md'  // 提高不透明度到95%
                  }`}
                >
                  <div className="whitespace-pre-wrap">
                    {message.content.split('【图片描述】').map((part, index) => {
                      if (index % 2 === 1) {
                        // 这是图片描述部分
                        return (
                          <div key={index} className="mt-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200">
                            <div className="flex items-center gap-2 mb-1 text-blue-600">
                              <Image size={14} />
                              <span className="text-xs font-medium">图片分析</span>
                            </div>
                            <p className="text-sm">{part}</p>
                          </div>
                        );
                      }
                      // 普通文本部分
                      return <span key={index}>{part}</span>;
                    })}
                  </div>
                  {message.fileIds && message.fileIds.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {message.fileIds.map((fileId) => {
                        const file = files[fileId];
                        return file ? (
                          <span 
                            key={fileId} 
                            className="text-xs bg-white/20 rounded px-1.5 py-0.5 cursor-pointer hover:bg-white/30"
                            onClick={() => setSelectedFileId(fileId)}
                          >
                            📄 {file.name}
                          </span>
                        ) : null;
                      })}
                    </div>
                  )}
                  <div className={`text-[10px] mt-1 ${message.type === 'user' ? 'text-blue-200' : 'text-slate-400'}`}>
                    {message.timestamp.toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-slate-100 rounded-2xl px-4 py-3">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                    <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 文档队列 - 放在输入框上方 */}
          <div className="px-3 pt-3 border-t border-slate-200 dark:border-slate-800">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-medium flex items-center gap-1">
                <Layers size={14} className="text-blue-500" />
                文档队列 ({fileList.length}/10)
              </h3>
              {fileList.length > 0 && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      if (selectedFile) {
                        setShowPreviewPanel(true);
                      } else {
                        alert('请先选择要预览的文档');
                      }
                    }}
                    className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
                  >
                    <Eye size={12} />
                    预览
                  </button>
                  <button
                    onClick={clearAllFiles}
                    className="text-xs text-red-600 hover:text-red-700"
                  >
                    清空
                  </button>
                </div>
              )}
            </div>
            <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto mb-2">
              {fileList.length === 0 ? (
                <div 
                  onClick={triggerFileInput}
                  className="w-full py-2 border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-lg flex items-center justify-center gap-1 text-slate-400 hover:border-blue-400 hover:bg-blue-50/50 cursor-pointer text-xs"
                >
                  <UploadCloud size={14} />
                  <span>点击上传文档</span>
                </div>
              ) : (
                fileList.map((file) => (
                  <div
                    key={file.id}
                    onClick={() => setSelectedFileId(file.id)}
                    className={`flex items-center gap-1 px-2 py-1 rounded-lg border text-xs cursor-pointer ${
                      selectedFileId === file.id
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                        : 'border-slate-200 dark:border-slate-700 hover:border-blue-300'
                    }`}
                  >
                    <FileText size={12} className="text-blue-500 shrink-0" />
                    <span className="max-w-[100px] truncate">{file.name}</span>
                    <div className="flex items-center gap-1">
                      {getStatusIcon(file.status)}
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeFile(file.id); }}
                      className="ml-1 p-0.5 hover:bg-slate-200 rounded"
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 输入区域 */}
          <div className="p-3 border-t border-slate-100/80 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-900/50">
            <div
              className="relative flex flex-col rounded-[24px] border border-slate-200/80 bg-white shadow-sm transition-all focus-within:border-blue-400/50 focus-within:shadow-md hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:focus-within:border-blue-500/50 dark:hover:border-slate-600"
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                  handleFileUpload({ target: { files: e.dataTransfer.files } } as any);
                }
              }}
            >
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={fileList.length > 0 ? "有什么我可以帮您的？" : "请先上传文档进行分析..."}
                className="max-h-[160px] min-h-[56px] w-full resize-none bg-transparent px-5 pt-4 pb-2 text-[14px] leading-relaxed text-slate-800 placeholder:text-slate-400 outline-none dark:text-slate-200 custom-scrollbar disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isLoading || fileList.length === 0}
              />
              <div className="flex items-center justify-between px-3 pb-2.5 pt-1">
                <div className="flex items-center gap-2">
                  <button
                    onClick={triggerFileInput}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-100/80 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                    title="上传附加文件"
                  >
                    <Plus size={16} />
                  </button>
                </div>
                <div className="flex items-center gap-3">
                  {isLoading ? (
                    <button
                      onClick={() => {
                        if (abortControllerRef.current) {
                          abortControllerRef.current.abort();
                          abortControllerRef.current = null;
                          setIsLoading(false);
                        }
                      }}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full transition-all duration-300 bg-amber-500 text-white shadow-sm shadow-amber-500/20 hover:bg-amber-600 hover:scale-105 active:scale-95"
                      title="停止生成"
                    >
                      <X size={14} />
                    </button>
                  ) : (
                    <button
                      onClick={sendMessage}
                      disabled={!inputText.trim() || fileList.length === 0}
                      className={`inline-flex h-8 w-8 items-center justify-center rounded-full transition-all duration-300 ${
                        !inputText.trim() || fileList.length === 0
                          ? 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-slate-800/80 dark:text-slate-500'
                          : 'bg-[#a3b8d7] text-white shadow-sm hover:bg-[#8ba3c7] hover:scale-105 active:scale-95 dark:bg-blue-600 dark:hover:bg-blue-700'
                      }`}
                    >
                      <Send size={14} className="ml-0.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 右侧预览区 - 只在 showPreviewPanel 为 true 时显示 */}
        {showPreviewPanel && selectedFile && (
          <div className="flex-1 flex flex-col backdrop-blur-xl bg-white/60 dark:bg-slate-900/60 rounded-2xl border border-blue-200/40 dark:border-blue-800/40 h-full relative overflow-hidden shadow-xl shadow-blue-500/10 animate-slideIn">
            {/* 关闭预览按钮 */}
            <button
              onClick={() => setShowPreviewPanel(false)}
              className="absolute top-4 right-4 z-20 p-2 bg-white dark:bg-slate-800 rounded-lg shadow-lg hover:bg-slate-100 dark:hover:bg-slate-700"
              title="关闭预览"
            >
              <X size={16} />
            </button>

            {/* 浮动工具栏 */}
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 h-10 px-3 bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 flex items-center gap-2">
              <button onClick={handleZoomOut} className="p-1.5 hover:bg-slate-100 rounded-lg">
                <ZoomOut size={16} />
              </button>
              <span className="text-xs w-10 text-center">{Math.round(scale * 100)}%</span>
              <button onClick={handleZoomIn} className="p-1.5 hover:bg-slate-100 rounded-lg">
                <ZoomIn size={16} />
              </button>
              <button onClick={handleRotate} className="p-1.5 hover:bg-slate-100 rounded-lg">
                <RotateCw size={16} />
              </button>
              <div className="w-px h-4 bg-slate-200" />
              <button
                onClick={() => downloadFile(selectedFile)}
                className="p-1.5 hover:bg-slate-100 rounded-lg"
                title="下载文件"
              >
                <Download size={16} />
              </button>
            </div>

            {/* 预览内容 */}
            <div className="flex-1 overflow-auto p-0 mt-12 flex items-center justify-center min-h-0">
              <div className="flex items-center justify-center w-full h-full">
                <div 
                  className="transition-transform"
                  style={{ transform: `scale(${scale}) rotate(${rotation}deg)` }}
                >
                  <div className="w-[600px] h-[800px] bg-white dark:bg-slate-800 border border-slate-200 rounded-lg shadow-xl overflow-auto p-6">
                    {selectedFile.status === 'processing' || selectedFile.status === 'converting' ? (
                      // 处理中状态
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                          <Loader size={40} className="animate-spin text-blue-500 mx-auto mb-4" />
                          <p className="text-sm text-slate-500">
                            {selectedFile.status === 'converting' ? '正在转换文档为PDF...' : '正在处理文档...'}
                          </p>
                          {selectedFile.progress && (
                            <p className="text-xs text-slate-400 mt-2">进度: {selectedFile.progress}%</p>
                          )}
                        </div>
                      </div>
                    ) : selectedFile.name?.toLowerCase().endsWith('.pdf') || selectedFile.type === 'application/pdf' ? (
                      // PDF预览
                      <div className="w-full h-full">
                        {previewUrl ? (
                          <iframe
                            src={previewUrl}
                            className="w-full h-full min-h-[600px] border-0"
                            title="PDF预览"
                          />
                        ) : (
                          <div className="flex items-center justify-center h-full">
                            <Loader size={40} className="animate-spin text-blue-500" />
                          </div>
                        )}
                      </div>
                    ) : ['.xlsx', '.xls'].some(ext => selectedFile.name?.toLowerCase().endsWith(ext)) ? (
                      // Excel预览 - 使用ExcelPreview组件
                      <ExcelPreview file={selectedFile} />
                    ) : ['.txt', '.md', '.markdown', '.csv'].some(ext => selectedFile.name?.toLowerCase().endsWith(ext)) ? (
                      // 文本文件预览 - TXT, MD, CSV
                      previewText ? (
                        <div className="flex flex-col h-full">
                          {/* 文本预览内容 */}
                        </div>
                      ) : (
                        <div className="flex items-center justify-center h-full">
                          <Loader size={40} className="animate-spin text-purple-500" />
                        </div>
                      )
                    ) : ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml', 'image/bmp'].includes(selectedFile.type) && previewUrl ? (
                      // 图片预览
                      <img 
                        src={previewUrl} 
                        alt={selectedFile.name}
                        className="max-w-full max-h-full object-contain"
                      />
                    ) : (
                      // 其他文件类型
                      <div className="flex flex-col items-center justify-center h-full text-center p-8">
                        {/* 其他文件类型内容 */}
                      </div>
                    )}
                  </div>
                </div>  
              </div> 
            </div>
          </div>
        )}
      </div>

      {/* 隐藏的文件输入 */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        accept=".pdf,.doc,.docx,.txt,.xlsx,.md,.jpg,.jpeg,.png,.gif,.bmp,.webp"
        multiple
        className="hidden"
      />

      {/* 修改预览对话框 */}
      {showPreview && pendingModifications && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl rounded-2xl p-6 max-w-4xl w-full mx-4 shadow-2xl shadow-blue-500/20 border border-blue-200/30 dark:border-blue-800/30 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold">预览修改效果</h3>
              <button 
                onClick={() => {
                  setShowPreview(false);
                  if (pdfPreviewUrl) {
                    URL.revokeObjectURL(pdfPreviewUrl);
                    setPdfPreviewUrl(null);
                  }
                  setShowPdfPreview(false);
                }} 
                className="p-2 hover:bg-slate-100 rounded-lg"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="mb-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <h4 className="font-semibold mb-2">将执行以下修改：</h4>
              {pendingModifications.modifications?.map((mod, index) => (
                <div key={index} className="text-sm mb-3 p-3 bg-white dark:bg-slate-800 rounded border border-blue-200 dark:border-blue-800">
                  
                  {/* 格式化标题（format_title） */}
                  {mod.type === 'format_title' && (
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-medium text-blue-600 dark:text-blue-400">📝 格式化标题</span>
                      </div>
                      <div className="ml-4 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-slate-500">目标：</span>
                          <span className="font-mono bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-sm">
                            {mod.target || '2021年民政事业发展统计公报'}
                          </span>
                        </div>
                        <div className="flex gap-3">
                          {mod.changes?.bold && (
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                              <span className="font-bold">B</span>
                              <span>加粗</span>
                            </span>
                          )}
                          {mod.changes?.color && (
                            <span className="inline-flex items-center gap-2 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                              <span>颜色：</span>
                              <span 
                                className="w-4 h-4 rounded-full border border-gray-300" 
                                style={{ backgroundColor: mod.changes.color.startsWith('#') ? mod.changes.color : `#${mod.changes.color}` }}
                              />
                              <span className="font-mono text-xs">{mod.changes.color}</span>
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 文本格式化（text_run_format） */}
                  {mod.type === 'text_run_format' && (
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-medium text-blue-600 dark:text-blue-400">✏️ 文本格式化</span>
                      </div>
                      <div className="ml-4 space-y-1">
                        <div>段落索引: {mod.paragraph_index}</div>
                        <div>文本块: {mod.run_indices?.join(', ') || '全部'}</div>
                        <div className="flex gap-3">
                          {mod.bold && (
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                              <span className="font-bold">B</span> 加粗
                            </span>
                          )}
                          {mod.color && (
                            <span className="inline-flex items-center gap-2 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                              <span>颜色：</span>
                              <span 
                                className="w-4 h-4 rounded-full border border-gray-300" 
                                style={{ backgroundColor: mod.color.startsWith('#') ? mod.color : `#${mod.color}` }}
                              />
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            
            <div className="mb-6 bg-slate-50 dark:bg-slate-800 rounded-lg overflow-hidden border border-slate-200">
              {showPdfPreview && pdfPreviewUrl ? (
                <iframe
                  src={pdfPreviewUrl}
                  className="w-full h-[600px] border-0"
                  title="PDF预览"
                />
              ) : previewFile ? (
                <div className="p-8 text-center">
                  <FileText size={64} className="mx-auto mb-4 text-blue-500" />
                  <p className="text-sm text-slate-700 dark:text-slate-300 mb-4">
                    点击下方按钮转换为PDF格式查看预览效果
                  </p>
                  <button
                    onClick={async () => {
                      try {
                        setIsLoading(true);
                        
                        const binaryString = atob(previewFile.content);
                        const bytes = new Uint8Array(binaryString.length);
                        for (let i = 0; i < binaryString.length; i++) {
                          bytes[i] = binaryString.charCodeAt(i);
                        }
                        const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
                        
                        const formData = new FormData();
                        formData.append('file', blob, previewFile.name);
                        
                        const response = await fetch(`${UNIFIED_API_URL}/convert/docx-to-pdf`, {
                          method: 'POST',
                          body: formData
                        });
                        
                        if (response.ok) {
                          const pdfBlob = await response.blob();
                          const pdfUrl = URL.createObjectURL(pdfBlob);
                          setPdfPreviewUrl(pdfUrl);
                          setShowPdfPreview(true);
                        } else {
                          alert('转换为PDF失败，请下载后查看');
                        }
                      } catch (error) {
                        console.error('转换失败:', error);
                        alert('预览失败，请重试');
                      } finally {
                        setIsLoading(false);
                      }
                    }}
                    className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium"
                    disabled={isLoading}
                  >
                    {isLoading ? '转换中...' : '📄 转换为PDF预览'}
                  </button>
                </div>
              ) : (
                <div className="text-center py-12">
                  <FileText size={48} className="mx-auto mb-4 text-gray-400" />
                  <p className="text-gray-500">正在准备预览...</p>
                </div>
              )}
            </div>
            
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowPreview(false);
                  if (pdfPreviewUrl) {
                    URL.revokeObjectURL(pdfPreviewUrl);
                    setPdfPreviewUrl(null);
                  }
                  setShowPdfPreview(false);
                }}
                className="px-4 py-2 border border-slate-300 rounded-lg hover:bg-slate-50"
              >
                取消
              </button>
              
              <button
                onClick={applyModifications}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                disabled={isLoading}
              >
                {isLoading ? '应用中...' : '确认应用修改'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 样式克隆模态框 */}
      {styleState.isOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-4xl w-full mx-4 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold">样式克隆</h3>
              <button onClick={closeStyleTransfer} className="p-2 hover:bg-slate-100 rounded-lg">
                <X size={20} />
              </button>
            </div>
            <div className="text-center py-8 text-slate-500">
              样式克隆开发中
            </div>
          </div>
        </div>
      )}
    </div>
  );
};