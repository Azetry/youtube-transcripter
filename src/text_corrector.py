"""文字自動校正模組 - 使用 OpenAI GPT 進行逐字稿校正"""

import os
from typing import Optional
from openai import OpenAI


class TextCorrector:
    """使用 GPT 進行逐字稿自動校正"""

    DEFAULT_SYSTEM_PROMPT = """你是一位專業的逐字稿校對編輯。你的任務是校正 Whisper 語音辨識產生的逐字稿。

校正原則：
1. 修正明顯的語音辨識錯誤（同音字、諧音字錯誤）
2. 修正標點符號，使文句通順
3. 修正專有名詞的錯誤拼寫
4. 保持原意，不要改寫或摘要內容
5. 保留口語化的表達方式，不要過度書面化
6. 分段落以提高可讀性

請直接輸出校正後的文字，不要加任何說明或註解。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model

    def correct(
        self,
        text: str,
        context: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """
        校正逐字稿文字

        Args:
            text: 原始逐字稿文字
            context: 額外上下文（如影片標題、主題），幫助理解專有名詞
            custom_prompt: 自訂系統提示詞（取代預設）

        Returns:
            校正後的文字
        """
        system_prompt = custom_prompt or self.DEFAULT_SYSTEM_PROMPT

        # 如果有上下文，加入系統提示
        if context:
            system_prompt += f"\n\n影片背景資訊：\n{context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,  # 較低的溫度以確保一致性
        )

        return response.choices[0].message.content

    def correct_with_terms(
        self,
        text: str,
        terms: list[str],
        context: Optional[str] = None,
    ) -> str:
        """
        校正逐字稿，並確保特定術語正確

        Args:
            text: 原始逐字稿文字
            terms: 需要正確辨識的專有名詞列表
            context: 額外上下文

        Returns:
            校正後的文字
        """
        terms_str = "、".join(terms)
        enhanced_prompt = self.DEFAULT_SYSTEM_PROMPT + f"""

特別注意以下專有名詞，確保它們被正確辨識：
{terms_str}"""

        return self.correct(text, context=context, custom_prompt=enhanced_prompt)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    corrector = TextCorrector()

    sample_text = """
    大家好歡迎來到今天的節目我們要來談談人工智慧的發展
    首先我想介紹一下open ai這家公司他們開發了chat gpt
    這個工具非常厲害可以回答各種問題
    """

    print("原始文字:")
    print(sample_text)
    print("\n校正中...")

    corrected = corrector.correct(sample_text)
    print("\n校正後文字:")
    print(corrected)
