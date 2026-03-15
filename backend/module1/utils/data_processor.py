"""
多任务数据处理工具
处理意图分类、实体识别、参数生成、风险检测的数据标注
"""

import json
import torch
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path
import random

logger = logging.getLogger(__name__)

class MultiTaskDataProcessor:
    """
    多任务数据处理器
    为同一个输入准备四个任务的标签
    """
    
    def __init__(self, config: Dict):
        self.config = config
        
        # 意图类别映射
        self.intent_map = {
            "format_heading": 0,        # 调整标题格式
            "format_paragraph": 1,       # 调整段落格式
            "insert_table": 2,           # 插入表格
            "delete_content": 3,         # 删除内容
            "modify_text": 4,            # 修改文本
            "calculate_sum": 5,           # 计算总和
            "calculate_average": 6,       # 计算平均值
            "analyze_trend": 7,           # 分析趋势
            "compare_data": 8,            # 对比数据
            "risk_check": 9,              # 风险检查
            "conflict_detection": 10,      # 矛盾检测
            "missing_check": 11,           # 缺失检查
            "export_pdf": 12,              # 导出PDF
            "convert_format": 13,          # 格式转换
            "merge_documents": 14,         # 合并文档
            "split_document": 15,          # 拆分文档
            "add_comment": 16,             # 添加评论
            "track_changes": 17,           # 修订追踪
            "apply_template": 18,          # 应用模板
            "custom_style": 19             # 自定义样式
        }
        
        # 实体类型映射（BIO标注）
        self.entity_map = {
            "O": 0,           # 非实体
            "B-TITLE": 1,     # 标题开始
            "I-TITLE": 2,     # 标题内部
            "B-VALUE": 3,     # 数值开始
            "I-VALUE": 4,     # 数值内部
            "B-DATE": 5,      # 日期开始
            "I-DATE": 6,      # 日期内部
            "B-AMOUNT": 7,    # 金额开始
            "I-AMOUNT": 8,    # 金额内部
            "B-COMPANY": 9,   # 公司名称开始
            "I-COMPANY": 10,  # 公司名称内部
            "B-PERSON": 11,   # 人名开始
            "I-PERSON": 12,   # 人名内部
            "B-LOCATION": 13, # 地点开始
            "I-LOCATION": 14  # 地点内部
        }
        
        # 风险类型映射
        self.risk_map = {
            "no_risk": 0,                 # 无风险
            "contract_conflict": 1,        # 合同条款冲突
            "missing_clause": 2,           # 缺少必要条款
            "amount_mismatch": 3,          # 金额不匹配
            "date_inconsistency": 4,       # 日期不一致
            "signature_missing": 5,        # 缺少签名
            "expired_document": 6,         # 文档已过期
            "compliance_violation": 7      # 合规违规
        }
        
        # 反向映射
        self.intent_reverse = {v: k for k, v in self.intent_map.items()}
        self.entity_reverse = {v: k for k, v in self.entity_map.items()}
        self.risk_reverse = {v: k for k, v in self.risk_map.items()}
        
        logger.info(f"数据处理器初始化完成")
        logger.info(f"意图类别数: {len(self.intent_map)}")
        logger.info(f"实体类型数: {len(self.entity_map)}")
        logger.info(f"风险类型数: {len(self.risk_map)}")
    
    def prepare_training_sample(self, text: str, annotations: Dict) -> Dict:
        """
        准备一个训练样本
        Args:
            text: 输入文本
            annotations: 包含四个任务的标注
        """
        sample = {
            'text': text,
            'intent_id': self.intent_map.get(annotations.get('intent', 'unknown'), 0),
            'entity_ids': self._convert_entity_sequence(annotations.get('entities', [])),
            'param_targets': self._encode_parameters(annotations.get('parameters', {})),
            'risk_id': self.risk_map.get(annotations.get('risk', 'no_risk'), 0)
        }
        return sample
    
    def _convert_entity_sequence(self, entities: List[str]) -> List[int]:
        """将实体标注序列转换为ID序列"""
        # 如果entities为空，返回全0序列
        if not entities:
            return [0] * self.config.get('max_length', 512)
        
        # 截断或填充到max_length
        max_len = self.config.get('max_length', 512)
        entity_ids = [self.entity_map.get(e, 0) for e in entities]
        
        if len(entity_ids) > max_len:
            entity_ids = entity_ids[:max_len]
        else:
            # 用O(0)填充
            entity_ids.extend([0] * (max_len - len(entity_ids)))
        
        return entity_ids
    
    def _encode_parameters(self, params: Dict) -> torch.Tensor:
        """将参数编码为向量"""
        param_dim = self.config.get('param_dim', 128)
        param_vector = torch.zeros(param_dim)
        
        # 编码常见参数
        if 'font_size' in params:
            param_vector[0] = min(params['font_size'] / 72.0, 1.0)
        
        if 'color_rgb' in params:
            rgb = params['color_rgb']
            for i, val in enumerate(rgb[:3]):
                param_vector[i+1] = min(val / 255.0, 1.0)
        
        if 'table_rows' in params:
            param_vector[10] = min(params['table_rows'] / 20.0, 1.0)
        
        if 'table_cols' in params:
            param_vector[11] = min(params['table_cols'] / 10.0, 1.0)
        
        if 'alignment' in params:
            alignment_map = {'left': 0.25, 'center': 0.5, 'right': 0.75, 'justify': 1.0}
            param_vector[12] = alignment_map.get(params['alignment'], 0.5)
        
        if 'bold' in params:
            param_vector[13] = 1.0 if params['bold'] else 0.0
        
        if 'italic' in params:
            param_vector[14] = 1.0 if params['italic'] else 0.0
        
        if 'underline' in params:
            param_vector[15] = 1.0 if params['underline'] else 0.0
        
        return param_vector
    
    def decode_parameters(self, param_vector: torch.Tensor) -> Dict:
        """将参数向量解码为参数字典"""
        params = {}
        
        if param_vector[0] > 0:
            params['font_size'] = int(param_vector[0] * 72)
        
        if torch.any(param_vector[1:4] > 0):
            params['color_rgb'] = [int(v * 255) for v in param_vector[1:4]]
        
        if param_vector[10] > 0:
            params['table_rows'] = int(param_vector[10] * 20)
        
        if param_vector[11] > 0:
            params['table_cols'] = int(param_vector[11] * 10)
        
        alignment_map = {0.25: 'left', 0.5: 'center', 0.75: 'right', 1.0: 'justify'}
        if param_vector[12] > 0:
            closest = min(alignment_map.keys(), key=lambda x: abs(x - param_vector[12].item()))
            params['alignment'] = alignment_map[closest]
        
        if param_vector[13] > 0.5:
            params['bold'] = True
        
        if param_vector[14] > 0.5:
            params['italic'] = True
        
        if param_vector[15] > 0.5:
            params['underline'] = True
        
        return params
    
    def save_mappings(self, save_path: Path):
        """保存映射表"""
        mappings = {
            'intent_map': self.intent_map,
            'entity_map': self.entity_map,
            'risk_map': self.risk_map,
            'intent_reverse': self.intent_reverse,
            'entity_reverse': self.entity_reverse,
            'risk_reverse': self.risk_reverse
        }
        
        with open(save_path / "mappings.json", "w", encoding='utf-8') as f:
            json.dump(mappings, f, ensure_ascii=False, indent=2)
        
        logger.info(f"映射表已保存到 {save_path / 'mappings.json'}")
    
    def load_mappings(self, load_path: Path):
        """加载映射表"""
        with open(load_path / "mappings.json", "r", encoding='utf-8') as f:
            mappings = json.load(f)
            
        self.intent_map = mappings['intent_map']
        self.entity_map = mappings['entity_map']
        self.risk_map = mappings['risk_map']
        self.intent_reverse = mappings['intent_reverse']
        self.entity_reverse = mappings['entity_reverse']
        self.risk_reverse = mappings['risk_reverse']
        
        logger.info(f"映射表已从 {load_path} 加载")

