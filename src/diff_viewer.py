"""文字差異比較模組"""

import difflib
from dataclasses import dataclass
from typing import Literal


@dataclass
class DiffResult:
    """差異比較結果"""
    original: str
    corrected: str
    unified_diff: str
    html_diff: str
    change_count: int
    similarity_ratio: float


class DiffViewer:
    """比較原始轉譯與校正後文字的差異"""

    def compare(
        self,
        original: str,
        corrected: str,
        context_lines: int = 3,
    ) -> DiffResult:
        """
        比較兩段文字的差異

        Args:
            original: 原始文字
            corrected: 校正後文字
            context_lines: 在差異周圍顯示的上下文行數

        Returns:
            DiffResult 包含各種格式的差異
        """
        original_lines = original.splitlines(keepends=True)
        corrected_lines = corrected.splitlines(keepends=True)

        # 產生 unified diff
        unified = list(difflib.unified_diff(
            original_lines,
            corrected_lines,
            fromfile='原始轉譯',
            tofile='校正後',
            n=context_lines,
        ))
        unified_diff = ''.join(unified)

        # 產生 HTML diff
        differ = difflib.HtmlDiff()
        html_diff = differ.make_file(
            original_lines,
            corrected_lines,
            fromdesc='原始轉譯',
            todesc='校正後',
            context=True,
            numlines=context_lines,
        )

        # 計算變更數量
        matcher = difflib.SequenceMatcher(None, original, corrected)
        change_count = sum(
            1 for op, _, _, _, _ in matcher.get_opcodes()
            if op != 'equal'
        )

        return DiffResult(
            original=original,
            corrected=corrected,
            unified_diff=unified_diff,
            html_diff=html_diff,
            change_count=change_count,
            similarity_ratio=matcher.ratio(),
        )

    def get_inline_diff(
        self,
        original: str,
        corrected: str,
    ) -> str:
        """
        產生行內差異標記（適合終端機顯示）

        使用 - 標記刪除，+ 標記新增
        """
        matcher = difflib.SequenceMatcher(None, original, corrected)
        result = []

        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == 'equal':
                result.append(original[i1:i2])
            elif op == 'replace':
                result.append(f"[-{original[i1:i2]}-]")
                result.append(f"[+{corrected[j1:j2]}+]")
            elif op == 'delete':
                result.append(f"[-{original[i1:i2]}-]")
            elif op == 'insert':
                result.append(f"[+{corrected[j1:j2]}+]")

        return ''.join(result)

    def get_word_diff(
        self,
        original: str,
        corrected: str,
    ) -> list[tuple[str, str, str]]:
        """
        以詞為單位比較差異

        Returns:
            列表，每個元素為 (操作, 原始詞, 校正詞)
            操作: 'equal', 'replace', 'delete', 'insert'
        """
        # 簡單以空白和標點分詞
        import re

        def tokenize(text: str) -> list[str]:
            return re.findall(r'\S+|\s+', text)

        original_tokens = tokenize(original)
        corrected_tokens = tokenize(corrected)

        matcher = difflib.SequenceMatcher(None, original_tokens, corrected_tokens)
        result = []

        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            orig_part = ''.join(original_tokens[i1:i2])
            corr_part = ''.join(corrected_tokens[j1:j2])
            result.append((op, orig_part, corr_part))

        return result

    def save_html_diff(self, diff_result: DiffResult, output_path: str) -> None:
        """將 HTML 差異報告儲存到檔案"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(diff_result.html_diff)


def print_colored_diff(diff_result: DiffResult) -> None:
    """使用 rich 在終端機顯示彩色差異"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()

    console.print(Panel(
        f"相似度: {diff_result.similarity_ratio:.1%} | 變更處: {diff_result.change_count}",
        title="差異摘要",
    ))

    # 顯示 unified diff
    diff_text = Text()
    for line in diff_result.unified_diff.splitlines():
        if line.startswith('+') and not line.startswith('+++'):
            diff_text.append(line + '\n', style="green")
        elif line.startswith('-') and not line.startswith('---'):
            diff_text.append(line + '\n', style="red")
        elif line.startswith('@@'):
            diff_text.append(line + '\n', style="cyan")
        else:
            diff_text.append(line + '\n')

    console.print(Panel(diff_text, title="差異內容"))


if __name__ == "__main__":
    viewer = DiffViewer()

    original = """大家好歡迎來到今天的節目我們要來談談人工智慧的發展
首先我想介紹一下open ai這家公司他們開發了chat gpt
這個工具非常厲害可以回答各種問題"""

    corrected = """大家好，歡迎來到今天的節目，我們要來談談人工智慧的發展。

首先，我想介紹一下 OpenAI 這家公司，他們開發了 ChatGPT。這個工具非常厲害，可以回答各種問題。"""

    result = viewer.compare(original, corrected)

    print(f"相似度: {result.similarity_ratio:.1%}")
    print(f"變更處: {result.change_count}")
    print("\n=== Inline Diff ===")
    print(viewer.get_inline_diff(original, corrected))
    print("\n=== Unified Diff ===")
    print(result.unified_diff)
