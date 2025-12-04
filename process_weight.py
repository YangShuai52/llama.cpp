import torch
from safetensors.torch import load_file, save_file
import argparse
import logging

# 配置日志（方便查看处理过程）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def safe_reciprocal(tensor: torch.Tensor) -> torch.Tensor:
    """
    对张量安全取倒数（核心函数，处理边界情况）
    :param tensor: 输入张量（支持CPU/GPU、整数/浮点型）
    :return: 取倒数后的张量（浮点型，无inf/NaN）
    """
    # 1. 移到CPU处理（兼容GPU张量，避免设备冲突）
    tensor = tensor.cpu()

    # 2. 整数型张量转为浮点型（PyTorch整数张量不支持倒数）
    if not torch.is_floating_point(tensor):
        logger.info(f"整数张量转为浮点型（原dtype: {tensor.dtype} → 新dtype: torch.float32）")
        tensor = tensor.to(torch.float32)

    # 3. 处理0值（替换为1e-8，避免取倒数生成inf）
    tensor_clamped = tensor.clamp(min=1e-8)

    # 4. 取倒数（非原地操作，避免修改原张量）
    tensor_reciprocal = tensor_clamped.reciprocal()

    # 5. 检查是否有异常值（inf/NaN）
    if torch.isinf(tensor_reciprocal).any():
        logger.warning("张量中存在inf值（已通过clamp处理，可忽略）")
    if torch.isnan(tensor_reciprocal).any():
        logger.error("张量中存在NaN值！请检查原始数据")

    return tensor_reciprocal

def process_input_scale_tensors(input_path: str, output_path: str = None) -> None:
    """
    处理Safetensors文件中.input_scale结尾的张量
    :param input_path: 输入Safetensors文件路径
    :param output_path: 输出修改后文件的路径（None则不保存）
    """
    # 1. 读取Safetensors文件
    try:
        tensors = load_file(input_path)
        logger.info(f"成功读取Safetensors文件: {input_path}")
        logger.info(f"文件中总张量数: {len(tensors)}")
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return

    # 2. 初始化计数器：统计处理的.input_scale张量数量
    processed_count = 0  # 核心新增：初始化计数器
    modified_tensors = {}  # 存储修改后的张量

    # 3. 筛选并处理.input_scale结尾的张量
    for name, tensor in tensors.items():
        if name.endswith(".input_scale"):
            processed_count += 1  # 核心新增：每处理一个，计数器+1
            logger.info(f"\n===== 处理第 {processed_count} 个张量: {name} =====")
            # 打印处理前信息
            logger.info(f"处理前 - 形状: {tensor.shape}, dtype: {tensor.dtype}, 设备: {tensor.device}")
            logger.info(f"处理前 - 前10个值: {tensor.cpu()[:10]}")

            # 安全取倒数
            tensor_reciprocal = safe_reciprocal(tensor)

            # 打印处理后信息
            logger.info(f"处理后 - 形状: {tensor_reciprocal.shape}, dtype: {tensor_reciprocal.dtype}")
            logger.info(f"处理后 - 前10个值: {tensor_reciprocal[:10]}")

            # 保存修改后的张量（覆盖原张量）
            modified_tensors[name] = tensor_reciprocal
        elif name.endswith(".bias"):
            # 非.input_scale张量，保留原值
            processed_count += 1  # 核心新增：每处理一个，计数器+1
            logger.info(f"\n===== 处理第 {processed_count} 个张量: {name} =====")
            # 打印处理前信息
            logger.info(f"处理前 - 形状: {tensor.shape}, dtype: {tensor.dtype}, 设备: {tensor.device}")
            logger.info(f"处理前 - 前10个值: {tensor.cpu()[:10]}")
            # 安全取倒数
            tensor_zero = torch.zeros_like(tensor)
                        # 打印处理后信息
            logger.info(f"处理后 - 形状: {tensor_zero.shape}, dtype: {tensor_zero.dtype}")
            logger.info(f"处理后 - 前10个值: {tensor_zero[:10]}")

            # 保存修改后的张量（覆盖原张量）
            modified_tensors[name] = tensor_zero


        else :
             modified_tensors[name] = tensor
    # 核心新增：打印总处理数量
    logger.info(f"\n===== 处理完成 ======")
    logger.info(f"文件中以.input_scale结尾的张量总数: {processed_count}")
    logger.info(f"成功处理 {processed_count} 个.input_scale张量")

    # 4. 可选：保存修改后的张量到新文件
    if output_path:
        try:
            save_file(modified_tensors, output_path)
            logger.info(f"成功保存修改后的文件: {output_path}")
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
    else:
        logger.info("未指定输出路径，不保存修改后的文件")

if __name__ == "__main__":
    # 命令行参数解析（方便终端运行）
    parser = argparse.ArgumentParser(description="处理Safetensors文件中.input_scale结尾的张量，取倒数")
    parser.add_argument("--input", required=True, help="输入Safetensors文件路径（如: ./model.safetensors）")
    parser.add_argument("--output", default=None, help="输出修改后文件的路径（可选，如: ./model_modified.safetensors）")
    args = parser.parse_args()

    # 执行处理
    process_input_scale_tensors(args.input, args.output)
