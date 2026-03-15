"""
模块一主程序入口
文档智能操作交互系统
"""

import sys
from pathlib import Path
import logging

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent))

from inference.predict import UnifiedIntentPredictor
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Module1:
    """
    模块一：文档智能操作交互系统
    """
    
    def __init__(self):
        logger.info("初始化模块一...")
        
        # 初始化意图预测器
        self.predictor = UnifiedIntentPredictor()
        
        logger.info("✅ 模块一初始化完成")
    
    def process_instruction(self, instruction: str, document_context: str = ""):
        """
        处理用户指令
        
        Args:
            instruction: 用户指令
            document_context: 文档上下文
        
        Returns:
            处理结果
        """
        logger.info(f"处理指令: {instruction}")
        
        # 1. 意图识别
        intent_result = self.predictor.predict(
            instruction, 
            document_context,
            return_probs=True
        )
        
        # 2. 根据意图执行相应操作
        if intent_result['confidence'] < 0.7:
            logger.warning(f"置信度较低: {intent_result['confidence']:.2f}")
            return {
                'status': 'low_confidence',
                'message': '无法准确理解指令意图',
                'details': intent_result
            }
        
        # 3. 返回处理结果
        result = {
            'status': 'success',
            'instruction': instruction,
            'intent': intent_result['intent'],
            'risk': intent_result['risk'],
            'parameters': intent_result['parameters'],
            'confidence': intent_result['confidence']
        }
        
        logger.info(f"处理完成: {result['intent']}")
        return result
    
    def batch_process(self, instructions: list):
        """批量处理指令"""
        logger.info(f"批量处理 {len(instructions)} 条指令")
        return self.predictor.predict_batch(instructions)

def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("文档智能操作交互系统 - 模块一")
    logger.info("=" * 50)
    
    # 初始化模块
    module = Module1()
    
    # 测试指令
    test_instructions = [
        "把标题改成红色",
        "在文档开头插入表格",
        "检查合同风险"
    ]
    
    for instruction in test_instructions:
        result = module.process_instruction(instruction)
        print(f"\n指令: {result['instruction']}")
        print(f"意图: {result['intent']}")
        print(f"参数: {result['parameters']}")
        print(f"置信度: {result['confidence']:.2f}")

if __name__ == "__main__":
    main()

