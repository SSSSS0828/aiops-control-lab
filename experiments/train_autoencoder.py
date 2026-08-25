"""轻量时序自编码器实验。

脚本只用于离线学习和对比，不进入在线控制面镜像。模型以正常窗口训练，
使用重建误差的 99 分位数作为异常阈值，并输出带真值序列上的 Precision/Recall。
"""

from pathlib import Path

import numpy as np
import torch
from fault_dataset import generate_samples
from torch import nn


class Autoencoder(nn.Module):
    """将 30 点时间窗口压缩到 8 维再重建。"""

    def __init__(self, window_size: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(window_size, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 16),
            nn.ReLU(),
            nn.Linear(16, window_size),
        )

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        """重建输入窗口，不直接输出异常分类。"""

        return self.network(values)


def build_windows(
    values: np.ndarray,
    labels: np.ndarray,
    size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """把连续序列转换为滑动窗口，并以窗口末端标签作为真值。"""

    windows = np.stack([values[index - size : index] for index in range(size, len(values))])
    targets = labels[size:]
    return windows.astype(np.float32), targets


def main() -> None:
    """训练模型、确定阈值并保存可复现实验结果。"""

    # 固定 NumPy 与 PyTorch 种子，使损失和指标在同一硬件上可重复。
    np.random.seed(42)
    torch.manual_seed(42)
    samples = generate_samples()
    values = np.asarray([sample.value for sample in samples], dtype=np.float32)
    labels = np.asarray([sample.anomalous for sample in samples], dtype=bool)
    # 使用正常训练段统计量标准化，绝不把异常段均值泄漏进预处理。
    normal_training = values[:240]
    mean = float(normal_training.mean())
    standard_deviation = float(normal_training.std())
    normalized = (values - mean) / max(standard_deviation, 1e-6)
    windows, targets = build_windows(normalized, labels, 30)
    training_windows = torch.from_numpy(windows[:210])

    model = Autoencoder(window_size=30)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_function = nn.MSELoss()
    for _ in range(30):
        # 每轮先清除旧梯度，否则 PyTorch 会默认累加梯度。
        optimizer.zero_grad()
        reconstructed = model(training_windows)
        loss = loss_function(reconstructed, training_windows)
        loss.backward()
        optimizer.step()

    with torch.no_grad():
        all_windows = torch.from_numpy(windows)
        errors = ((model(all_windows) - all_windows) ** 2).mean(dim=1).numpy()
    # 只使用正常训练窗口的误差分布选择阈值，避免用测试标签调参。
    threshold = float(np.quantile(errors[:210], 0.99))
    predicted = errors > threshold
    true_positive = int(np.logical_and(predicted, targets).sum())
    false_positive = int(np.logical_and(predicted, ~targets).sum())
    false_negative = int(np.logical_and(~predicted, targets).sum())
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)

    output = Path(__file__).parent / "results" / "autoencoder-v1.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"threshold={threshold:.6f}\nprecision={precision:.4f}\nrecall={recall:.4f}\n",
        encoding="utf-8",
    )
    torch.save(
        {"state_dict": model.state_dict(), "mean": mean, "std": standard_deviation},
        output.with_suffix(".pt"),
    )
    print(f"自编码器实验结果已写入：{output}")


if __name__ == "__main__":
    main()
