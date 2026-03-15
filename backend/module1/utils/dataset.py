"""
多任务数据集类
用于加载和批处理训练数据
"""

import torch
from torch.utils.data import Dataset, DataLoader
from transformers import BertTokenizer
from typing import Dict, List, Optional
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class UnifiedDataset(Dataset):
    """
    统一的多任务数据集
    """
    
    def __init__(
        self,
        data_path: Optional[Path] = None,
        data_list: Optional[List[Dict]] = None,
        tokenizer: Optional[BertTokenizer] = None,
        max_length: int = 512,
        is_training: bool = True
    ):
        self.max_length = max_length
        self.tokenizer = tokenizer
        self.is_training = is_training
        
        # 加载数据
        if data_path is not None:
            self.data = self._load_data(data_path)
        elif data_list is not None:
            self.data = data_list
        else:
            self.data = []
        
        logger.info(f"数据集初始化完成，共 {len(self.data)} 个样本")
    
    def _load_data(self, data_path: Path) -> List[Dict]:
        """加载数据文件"""
        data = []
        
        # 支持多种文件格式
        if data_path.suffix == '.json':
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        elif data_path.suffix == '.jsonl':
            with open(data_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data.append(json.loads(line))
        else:
            logger.error(f"不支持的文件格式: {data_path.suffix}")
        
        logger.info(f"从 {data_path} 加载了 {len(data)} 个样本")
        return data
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        item = self.data[idx]
        
        # 编码文本
        encoding = self.tokenizer(
            item['text'],
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        # 处理实体标签
        entity_ids = item.get('entity_ids', [0] * self.max_length)
        if len(entity_ids) > self.max_length:
            entity_ids = entity_ids[:self.max_length]
        elif len(entity_ids) < self.max_length:
            entity_ids.extend([-100] * (self.max_length - len(entity_ids)))
        
        return {
            'input_ids': encoding['input_ids'].squeeze(0),
            'attention_mask': encoding['attention_mask'].squeeze(0),
            'intent_id': torch.tensor(item['intent_id']),
            'entity_ids': torch.tensor(entity_ids, dtype=torch.long),
            'param_targets': item['param_targets'],  # 已经是tensor
            'risk_id': torch.tensor(item['risk_id'])
        }
    
    @staticmethod
    def collate_fn(batch):
        """自定义批处理函数"""
        input_ids = torch.stack([item['input_ids'] for item in batch])
        attention_mask = torch.stack([item['attention_mask'] for item in batch])
        intent_ids = torch.stack([item['intent_id'] for item in batch])
        entity_ids = torch.stack([item['entity_ids'] for item in batch])
        param_targets = torch.stack([item['param_targets'] for item in batch])
        risk_ids = torch.stack([item['risk_id'] for item in batch])
        
        return {
            'input_ids': input_ids,
            'attention_mask': attention_mask,
            'labels': {
                'intent_ids': intent_ids,
                'entity_ids': entity_ids,
                'param_targets': param_targets,
                'risk_ids': risk_ids
            }
        }

def create_dataloaders(
    train_data: List[Dict],
    dev_data: List[Dict],
    tokenizer: BertTokenizer,
    batch_size: int,
    max_length: int,
    num_workers: int = 2
) -> tuple:
    """创建训练和验证数据加载器"""
    
    train_dataset = UnifiedDataset(
        data_list=train_data,
        tokenizer=tokenizer,
        max_length=max_length,
        is_training=True
    )
    
    dev_dataset = UnifiedDataset(
        data_list=dev_data,
        tokenizer=tokenizer,
        max_length=max_length,
        is_training=False
    )
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=False,  # M1上设为False
        collate_fn=UnifiedDataset.collate_fn
    )
    
    dev_loader = DataLoader(
        dev_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=False,
        collate_fn=UnifiedDataset.collate_fn
    )
    
    logger.info(f"训练数据加载器创建完成: {len(train_loader)} batches")
    logger.info(f"验证数据加载器创建完成: {len(dev_loader)} batches")
    
    return train_loader, dev_loader

