"""Preprocess msmodelslim W8A8 weights before GGUF conversion.

Two transformations are needed:
1. input_scale tensors: take reciprocal (AscendQuant expects 1/scale)
2. bias tensors: zero out (W8A8 model does not use biases)

Usage:
    python process_weight.py --input model.safetensors --output model_processed.safetensors
"""

import argparse
import logging

import torch
from safetensors.torch import load_file, save_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def safe_reciprocal(tensor: torch.Tensor) -> torch.Tensor:
    tensor = tensor.cpu().float()
    tensor = tensor.clamp(min=1e-8)
    return tensor.reciprocal()


def process_safetensors(input_path: str, output_path: str) -> None:
    tensors = load_file(input_path)
    logger.info(f"Loaded {len(tensors)} tensors from {input_path}")

    modified = {}
    for name, tensor in tensors.items():
        if name.endswith(".input_scale"):
            logger.info(f"Reciprocal: {name} shape={tensor.shape}")
            modified[name] = safe_reciprocal(tensor)
        elif name.endswith(".bias"):
            logger.info(f"Zero bias: {name} shape={tensor.shape}")
            modified[name] = torch.zeros_like(tensor)
        else:
            modified[name] = tensor

    save_file(modified, output_path)
    logger.info(f"Saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preprocess msmodelslim W8A8 safetensors")
    parser.add_argument("--input",  required=True, help="Input safetensors path")
    parser.add_argument("--output", required=True, help="Output safetensors path")
    args = parser.parse_args()
    process_safetensors(args.input, args.output)
