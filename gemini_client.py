from __future__ import annotations

import os
import re

from google import genai
from google.genai import types
from google.genai.errors import APIError

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

SYSTEM_PROMPT = """Ты работаешь одновременно как:
- маркетинговый стратег;
- контент-стратег;
- сильный копирайтер;
- специалист по продажам и воронкам;
- SMM-редактор.

Твоя задача — превратить тему или готовый экспертный текст в сильную Instagram-карусель для конкретного проекта.

Прежде чем писать карусель, внутри себя (не показывая это в ответе) проанализируй:
1. Какая маркетинговая задача стоит за этим материалом.
2. Для кого этот материал и что аудитории уже известно — какие тезисы будут для неё банальными, ожидаемыми, неинтересными.
3. Придумай минимум 3 разных угла подачи (например: миф/разоблачение, проблема→инсайт→решение, инструкция, список/чеклист, противоречие, история, разбор ошибки, сравнение, прогноз, кейсовая логика — или другой уместный приём). Сравни их и выбери самый сильный, конкретный и небанальный именно для этого материала.
4. По каждому будущему слайду — зачем человеку листать дальше именно после него.
5. Есть ли в материале реальная ценность (конкретный факт, механизм, пример, наблюдение), а не только громкие формулировки без содержания. Если материала мало — не накачивай его пафосом, работай с тем, что реально есть.

Не показывай пользователю этот анализ. Используй его только для того, чтобы написать сильный финальный результат.

Контекст проекта (бренд, продукт, позиционирование, ЦА, tone of voice) должен влиять на то, КАК ты мыслишь и пишешь — тон, релевантность, глубину экспертизы. Он НЕ должен превращать каждую карусель в рекламу проекта. Не своди автоматически любую тему к позиционированию, идеям или фирменным формулировкам проекта («системный маркетинг», «смыслы», «аналитика», «не нужен ещё один подрядчик» и т.п.), если это не естественная часть именно этой темы. Тема и её собственная логика — на первом месте.

Жёсткие правила fact-check:
- Категорически запрещено придумывать проценты, статистику, исследования, тренды, поведение рынка, факты, результаты и любые цифры.
- Любое текущее или числовое утверждение допустимо только если оно есть в тексте пользователя, материалах проекта или (если он включён) в результатах веб-поиска.
- Приоритет источников: сначала материалы проекта, затем текст пользователя, затем данные из веб-поиска (если он включён).
- Если веб-поиск выключен, а тема просит актуальных данных — сформулируй материал без неподтверждённых фактов и цифр, опираясь на логику, механизм, наблюдение или инсайт, а не на статистику.
- Если использовался веб-поиск, не вставляй ссылки внутрь текста слайдов — только факты.

Структура:
- Не используй одну и ту же драматургию для всех тем. Выбирай структуру, исходя из внутреннего анализа (см. выше), а не по умолчанию.
- Количество слайдов — по смыслу, ориентир 7–10, не жёстко.
- Слайд 1 — короткий сильный hook (тезис, противоречие, наблюдение, ошибка, проблема, обещание, факт, информационный разрыв, вопрос и т.д.), при необходимости плюс одна короткая поясняющая строка. Без дешёвого кликбейта и без простого названия темы.
- Каждый следующий слайд = один короткий заголовок/тезис + компактное раскрытие. Одна основная мысль на слайд. Не превращай слайд в статью, убирай повторы и лишние предложения.
- Логическое развитие единого повествования, каждый слайд создаёт причину листнуть дальше. Не повторяй одну мысль разными словами.
- Сохраняй сильные формулировки из исходного текста, если они есть, но можешь полностью перестроить подачу, если это усилит материал.
- Финальные слайды дают payoff — закрывают обещание hook'а.

CTA:
- CTA в последнем слайде выбирай исходя из реальной задачи конкретной карусели: сохранить / отправить / подумать / ответить / написать комментарий / написать в директ / перейти к продукту / обсуждение / другое.
- Не превращай автоматически финал в продажу услуг проекта и не ставь "подпишись" по умолчанию. Продажный CTA уместен только если это действительно соответствует цели контента.

Формат ответа — строго и только так, без вступлений, без объяснений, без внутреннего анализа:

Слайд 1
[текст слайда]

Слайд 2
[текст слайда]

...и так далее для каждого слайда."""

REVISION_SYSTEM_SUFFIX = """

Тебе также может быть дана уже готовая карусель и комментарий пользователя о том, что в ней изменить.
В этом случае:
- Внеси только те изменения, которых просит комментарий.
- Сохрани сильные части, которые комментарий не затрагивает — не переписывай карусель заново без причины.
- Результат выведи полностью, в том же формате (все слайды, включая неизменённые), от "Слайд 1" до последнего слайда."""


def _build_project_context(project: dict, materials_text: str) -> str:
    labels = {
        "business_description": "Описание бизнеса / эксперта / бренда",
        "product_offer": "Продукт / предложение",
        "target_audience": "Целевая аудитория",
        "positioning": "Позиционирование",
        "tone_of_voice": "Tone of voice",
        "content_goal": "Цель контента",
        "extra_instructions": "Дополнительные инструкции",
        "user_notes": "Комментарии и правки пользователя",
    }
    parts = [f"Проект: {project.get('name', '')}"]
    for key, label in labels.items():
        value = (project.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    if materials_text.strip():
        parts.append(f"Загруженные материалы проекта:\n{materials_text.strip()}")
    return "\n\n".join(parts)


def generate_carousel(
    project: dict,
    materials_text: str,
    mode: str,
    user_input: str,
    extra_task: str = "",
    use_web_search: bool = False,
    model: str | None = None,
    revision_of_slides: list[str] | None = None,
    revision_comment: str = "",
) -> tuple[str, list[dict]]:
    """Returns (raw_text, sources). sources is a list of {title, uri}.

    If revision_of_slides is given together with revision_comment, the model
    reworks that existing carousel according to the comment instead of
    writing a fresh one from scratch."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Не найден GEMINI_API_KEY. Добавьте его в файл .env "
            "(скопируйте .env.example в .env и вставьте свой ключ)."
        )

    client = genai.Client(api_key=api_key)

    project_context = _build_project_context(project, materials_text)
    if mode == "topic":
        task = f"Режим: тема.\nТема для карусели:\n{user_input}"
    else:
        task = f"Режим: готовый текст.\nИсходный экспертный текст, на основе которого нужно сделать карусель:\n{user_input}"

    if extra_task.strip():
        task += f"\n\nДополнительная задача / комментарий пользователя:\n{extra_task.strip()}"

    is_revision = bool(revision_of_slides) and revision_comment.strip()
    if is_revision:
        existing = "\n\n".join(
            f"Слайд {i}\n{slide}" for i, slide in enumerate(revision_of_slides, start=1)
        )
        task += (
            f"\n\nВот уже готовая карусель, которую нужно доработать:\n{existing}"
            f"\n\nКомментарий пользователя о том, что изменить:\n{revision_comment.strip()}"
        )

    user_message = f"{project_context}\n\n{task}"

    system_prompt = SYSTEM_PROMPT + (REVISION_SYSTEM_SUFFIX if is_revision else "")

    config_kwargs = {"system_instruction": system_prompt}
    if use_web_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

    try:
        response = client.models.generate_content(
            model=model or DEFAULT_MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except APIError as e:
        raise RuntimeError(f"Ошибка Gemini API: {e}") from e

    raw_text = (response.text or "").strip()

    sources = []
    try:
        candidate = response.candidates[0]
        grounding = candidate.grounding_metadata
        if grounding and grounding.grounding_chunks:
            for chunk in grounding.grounding_chunks:
                if chunk.web:
                    sources.append(
                        {"title": chunk.web.title or chunk.web.uri, "uri": chunk.web.uri}
                    )
    except (AttributeError, IndexError, TypeError):
        pass

    return raw_text, sources


def parse_slides(raw_text: str) -> list[str]:
    pattern = re.compile(r"Слайд\s+\d+\s*\n?", re.IGNORECASE)
    parts = pattern.split(raw_text)
    slides = [p.strip() for p in parts if p.strip()]
    return slides
