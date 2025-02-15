import json
import aiohttp
from typing import Optional

async def generate_hint(question: str, answer: str, api_key: str, folder_id: str) -> Optional[str]:
    prompt = f"""
    Сгенерируй пояснение для ученика, который ошибся в ответе на вопрос. 
    Не называй правильный ответ напрямую. Используй подсказки.

    Вопрос: {question}
    Ошибочный ответ ученика: {answer}

    Формат:
    - Начни с позитивного подкрепления
    - Укажи на область ошибки
    - Предложи направление для размышлений
    """

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "x-folder-id": folder_id,
        "Content-Type": "application/json"
    }
    
    data = {
        "modelUri": f"gpt://{folder_id}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": 150
        },
        "messages": [
            {"role": "system", "text": "Ты — опытный преподаватель, помогаешь ученикам понять их ошибки"},
            {"role": "user", "text": prompt}
        ]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                result = await response.json()
                return result['result']['alternatives'][0]['message']['text']
            return None