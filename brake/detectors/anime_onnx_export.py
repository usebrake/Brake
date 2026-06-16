"""Install-time ONNX export for the optional illustrated detector.

This module intentionally contains the torch/transformers imports so the
long-lived runtime detector can be packaged without those heavy libraries.
"""
from __future__ import annotations

import gc
import importlib.util
import logging
from pathlib import Path

_log = logging.getLogger(__name__)


def dependencies_available() -> bool:
    return all(
        importlib.util.find_spec(m) is not None
        for m in ("transformers", "torch", "onnx")
    )


def export_to_onnx(
    root: Path,
    *,
    edge: int,
    fp32_name: str,
    int8_name: str,
    torch_weight_names: list[str],
) -> Path:
    import torch  # type: ignore[import-not-found]
    from onnxruntime.quantization import QuantType, quantize_dynamic  # type: ignore[import-not-found]
    from transformers import AutoModelForImageClassification  # type: ignore[import-not-found]

    fp32_path = root / fp32_name
    int8_path = root / int8_name

    _log.info("anime_nsfw: exporting ONNX model (one-time)...")
    model = AutoModelForImageClassification.from_pretrained(str(root))
    model.eval()
    dummy = torch.randn(1, 3, edge, edge)
    torch.onnx.export(
        model,
        (dummy,),
        str(fp32_path),
        input_names=["pixel_values"],
        output_names=["logits"],
        dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=14,
        do_constant_folding=True,
        dynamo=False,
    )
    quantize_dynamic(str(fp32_path), str(int8_path), weight_type=QuantType.QInt8)
    del model
    gc.collect()

    for name in (fp32_name, *torch_weight_names):
        try:
            (root / name).unlink(missing_ok=True)
        except OSError as e:
            _log.warning("anime_nsfw: could not remove %s post-export: %s", name, e)
    if not int8_path.exists():
        raise RuntimeError("onnx_export_failed")
    _log.info("anime_nsfw: ONNX model ready (%.0fMB).", int8_path.stat().st_size / 1e6)
    return int8_path
