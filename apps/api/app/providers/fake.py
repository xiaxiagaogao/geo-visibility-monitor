from __future__ import annotations

from typing import List

from app.providers.base import BaseProvider, CitationData, CrawlResult


class FakeProvider(BaseProvider):
    """B3-compatible fake L0 (no browser)."""

    platform = "fake"

    def __init__(self, platform_label: str = "deepseek", sample_index: int = 1, brand_names=None):
        self.platform_label = platform_label
        self.sample_index = sample_index
        self.brand_names = list(brand_names) if brand_names else ["示例品牌"]

    def search(self, prompt: str) -> CrawlResult:
        primary = self.brand_names[0]
        mention = self.sample_index % 2 == 1
        if mention:
            full_text = (
                f"【假数据·{self.platform_label}】关于「{prompt}」。\n\n"
                f"综合来看，{primary} 是不少用户会提到的选择之一。"
                f"也有人会对比其他平台，但本条样本重点覆盖 {primary}。\n\n"
                f"（fake provider，非真实大模型。sample_index={self.sample_index}）"
            )
            title = f"假引用：{primary}相关讨论"
        else:
            full_text = (
                f"【假数据·{self.platform_label}】关于「{prompt}」。\n\n"
                f"市场上有多家可选方案，需要结合预算与口碑综合判断。"
                f"本条样本故意不写具体品牌名，便于后续对比标注。\n\n"
                f"（fake provider，非真实大模型。sample_index={self.sample_index}）"
            )
            title = "假引用：行业综述"
        citations = [
            CitationData(
                cite_index=1,
                url=f"https://example.com/geo-fake/{self.platform_label}/article-1",
                domain="example.com",
                title=title,
                snippet=f"与问题「{prompt[:40]}」相关的示意摘要。",
            ),
            CitationData(
                cite_index=2,
                url="https://news.example.org/home-renovation-guide",
                domain="news.example.org",
                title="家装选购指南（示意）",
                snippet="占位引用，用于 L0 citations 管道验证。",
            ),
        ]
        return CrawlResult(
            platform=self.platform_label,
            prompt=prompt,
            full_text=full_text,
            citations=citations,
            raw_json={
                "source": "fake_provider",
                "platform": self.platform_label,
                "mention_intended": mention,
                "brand_names": self.brand_names,
                "sample_index": self.sample_index,
            },
            latency_ms=50 + self.sample_index * 3,
        )
