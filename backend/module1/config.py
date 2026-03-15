"""
模块一配置文件 - M1优化轻量版
"""

import os
from pathlib import Path

# 设置镜像源
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 基础路径配置
BASE_DIR = Path(__file__).parent.absolute()
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
CHECKPOINTS_DIR = BASE_DIR / "checkpoints"

# 模型配置 - 轻量版
MODEL_CONFIG = {
    "pretrained_model_name": "bert-base-chinese",
    "max_length": 128,  # 减小序列长度
    "num_intents": 20,
    "num_entity_types": 15,
    "param_dim": 64,  # 减小参数维度
    "num_risk_types": 8,
    "hidden_dropout_prob": 0.1,
    "attention_probs_dropout_prob": 0.1
}

# 训练配置 - 快速版
TRAIN_CONFIG = {
    "batch_size": 2,  # 小批量
    "learning_rate": 3e-4,  # 增大学习率
    "num_epochs": 3,  # 减少epoch
    "warmup_steps": 10,
    "weight_decay": 0.01,
    "gradient_accumulation_steps": 1,  # 关闭梯度累积
    "max_grad_norm": 1.0,
    "eval_steps": 10,
    "save_steps": 20,
    "logging_steps": 5
}

# 路径配置
PATH_CONFIG = {
    "raw_data_dir": DATA_DIR / "raw",
    "processed_data_dir": DATA_DIR / "processed",
    "annotations_dir": DATA_DIR / "annotations",
    "model_save_path": MODELS_DIR / "unified_model",
    "checkpoint_dir": CHECKPOINTS_DIR
}

# M1芯片优化配置
M1_CONFIG = {
    "use_mps": True,
    "num_workers": 0,  # M1上设为0
    "pin_memory": False,
    "memory_threshold": 6 * 1024 * 1024 * 1024
}

# 创建必要的目录
for path in [MODELS_DIR, DATA_DIR, CHECKPOINTS_DIR,
             PATH_CONFIG["raw_data_dir"],
             PATH_CONFIG["processed_data_dir"],
             PATH_CONFIG["annotations_dir"]]:
    path.mkdir(parents=True, exist_ok=True)
    print(f"✅ 确保目录存在: {path}")

print("✅ M1优化版配置文件加载完成！")
