import os

import streamlit as st
from dotenv import load_dotenv

import storage
from gemini_client import DEFAULT_MODEL, generate_carousel, parse_slides
from file_parser import extract_text

load_dotenv()
API_KEY_PRESENT = bool(os.getenv("GEMINI_API_KEY"))

st.set_page_config(page_title="Carousel App", layout="wide")

FIELD_LABELS = {
    "business_description": "Описание бизнеса / эксперта / бренда",
    "product_offer": "Продукт / предложение",
    "target_audience": "Целевая аудитория",
    "positioning": "Позиционирование",
    "tone_of_voice": "Tone of voice",
    "content_goal": "Цель контента",
    "extra_instructions": "Дополнительные инструкции",
    "user_notes": "Комментарии и правки пользователя",
}

if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []
if "last_context" not in st.session_state:
    st.session_state.last_context = None

# ---------- Sidebar: список проектов ----------
with st.sidebar:
    st.title("Проекты")

    if st.button("+ Новый проект", use_container_width=True):
        new_project = storage.create_project("Новый проект")
        st.session_state.current_project_id = new_project["id"]
        st.session_state.last_result = None
        st.session_state.last_sources = []
        st.session_state.last_context = None
        st.rerun()

    st.divider()

    projects = storage.list_projects()
    if not projects:
        st.caption("Пока нет проектов. Создайте первый.")
    for p in projects:
        is_active = p["id"] == st.session_state.current_project_id
        label = ("📌 " if is_active else "") + (p["name"] or "Без названия")
        if st.button(label, key=f"select_{p['id']}", use_container_width=True):
            st.session_state.current_project_id = p["id"]
            st.session_state.last_result = None
            st.session_state.last_sources = []
            st.rerun()

    st.divider()
    with st.expander("Настройки модели"):
        model_override = st.text_input("Модель Gemini", value=DEFAULT_MODEL)
        st.session_state.model_override = model_override

# ---------- Основное окно ----------
if not API_KEY_PRESENT:
    st.error(
        "Не найден GEMINI_API_KEY. Добавьте его в файл .env "
        "(скопируйте .env.example в .env и вставьте свой ключ)."
    )

if not st.session_state.current_project_id:
    st.title("Carousel App")
    st.write("Выберите проект слева или создайте новый, чтобы начать.")
    st.stop()

project = storage.load_project(st.session_state.current_project_id)
if project is None:
    st.session_state.current_project_id = None
    st.rerun()

st.title(f"Проект: {project['name']}")

tab_generate, tab_settings, tab_history = st.tabs(
    ["Создать карусель", "Настройки проекта", "История"]
)

# ---------- Настройки проекта ----------
with tab_settings:
    with st.form("project_settings_form"):
        name = st.text_input("Название проекта", value=project.get("name", ""))

        updated_fields = {}
        for field, label in FIELD_LABELS.items():
            updated_fields[field] = st.text_area(
                label, value=project.get(field, ""), height=100
            )

        st.markdown("**Загруженные материалы**")
        materials = project.get("materials", [])
        if materials:
            for m in materials:
                st.caption(f"• {m['original_name']}")
        else:
            st.caption("Материалы не загружены.")

        uploaded_files = st.file_uploader(
            "Добавить материалы (PDF, DOCX, TXT, MD)",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
        )

        submitted = st.form_submit_button("Сохранить проект")

        if submitted:
            project["name"] = name.strip() or "Без названия"
            project.update(updated_fields)

            if uploaded_files:
                for uf in uploaded_files:
                    content = uf.read()
                    path = storage.save_uploaded_file(project["id"], uf.name, content)
                    project.setdefault("materials", []).append(
                        {"original_name": uf.name, "path": path}
                    )

            storage.save_project(project)
            st.success("Проект сохранён.")
            st.rerun()

    if project.get("materials"):
        st.markdown("**Управление материалами**")
        for m in project["materials"]:
            col1, col2 = st.columns([4, 1])
            col1.caption(m["original_name"])
            if col2.button("Удалить", key=f"del_{m['path']}"):
                storage.remove_material_file(m["path"])
                project["materials"] = [
                    x for x in project["materials"] if x["path"] != m["path"]
                ]
                storage.save_project(project)
                st.rerun()

    st.divider()
    if st.button("Удалить проект", type="secondary"):
        st.session_state.confirm_delete = True

    if st.session_state.get("confirm_delete"):
        st.warning("Удалить проект без возможности восстановления?")
        c1, c2 = st.columns(2)
        if c1.button("Да, удалить"):
            for m in project.get("materials", []):
                storage.remove_material_file(m["path"])
            storage.delete_project(project["id"])
            st.session_state.current_project_id = None
            st.session_state.confirm_delete = False
            st.rerun()
        if c2.button("Отмена"):
            st.session_state.confirm_delete = False
            st.rerun()

# ---------- Генерация карусели ----------
with tab_generate:
    mode_label = st.radio("Режим", ["Тема", "Готовый текст"], horizontal=True)
    mode = "topic" if mode_label == "Тема" else "text"

    placeholder = (
        "Опишите тему, о которой хотите сделать карусель..."
        if mode == "topic"
        else "Вставьте готовый экспертный текст..."
    )
    user_input = st.text_area("Ввод", height=250, placeholder=placeholder)

    extra_task = st.text_input(
        "Дополнительная задача / комментарий (опционально)",
        placeholder="Например: сделай акцент на цене, или используй более дерзкий тон",
    )

    use_web_search = False

    generate_clicked = st.button(
        "Создать карусель", type="primary", disabled=not API_KEY_PRESENT
    )

    if generate_clicked:
        if not user_input.strip():
            st.warning("Введите тему или текст.")
        else:
            materials_text = ""
            read_errors = []
            for m in project.get("materials", []):
                text = extract_text(m["path"])
                if text.startswith("[Не удалось прочитать файл"):
                    read_errors.append(text)
                else:
                    materials_text += f"\n\n--- {m['original_name']} ---\n{text}"

            for err in read_errors:
                st.warning(err)

            with st.spinner("Gemini анализирует материал и собирает карусель..."):
                try:
                    raw, sources = generate_carousel(
                        project,
                        materials_text,
                        mode,
                        user_input,
                        extra_task=extra_task,
                        use_web_search=use_web_search,
                        model=st.session_state.get("model_override") or None,
                    )
                    slides = parse_slides(raw)
                    st.session_state.last_result = slides
                    st.session_state.last_sources = sources
                    st.session_state.last_context = {
                        "mode": mode,
                        "mode_label": mode_label,
                        "user_input": user_input,
                        "extra_task": extra_task,
                        "use_web_search": use_web_search,
                        "materials_text": materials_text,
                    }

                    storage.add_history_entry(
                        project,
                        {
                            "mode": mode_label,
                            "input_preview": user_input.strip()[:200],
                            "slides": slides,
                            "sources": sources,
                        },
                    )
                except RuntimeError as e:
                    st.session_state.last_result = None
                    st.session_state.last_sources = []
                    st.error(str(e))
                except Exception as e:
                    st.session_state.last_result = None
                    st.session_state.last_sources = []
                    st.error(f"Непредвиденная ошибка: {e}")

    if st.session_state.last_result:
        st.divider()
        st.subheader("Результат")
        for i, slide in enumerate(st.session_state.last_result, start=1):
            with st.container(border=True):
                st.markdown(f"**Слайд {i}**")
                st.write(slide)

        if st.session_state.last_sources:
            st.divider()
            st.markdown("**Источники**")
            for s in st.session_state.last_sources:
                st.caption(f"• [{s['title']}]({s['uri']})")

        st.divider()
        revision_comment = st.text_input(
            "Что изменить в этой карусели?",
            key="revision_comment_input",
            placeholder="Например: убери слайд про цифры, сделай тон мягче",
        )
        remember_edit = st.checkbox(
            "Запомнить эту правку для проекта", key="remember_edit_checkbox"
        )
        rework_clicked = st.button(
            "Переработать с учётом комментария", disabled=not API_KEY_PRESENT
        )

        if rework_clicked:
            if not revision_comment.strip():
                st.warning("Опишите, что нужно изменить.")
            elif not st.session_state.last_context:
                st.warning("Нет предыдущей генерации для доработки.")
            else:
                ctx = st.session_state.last_context
                with st.spinner("Gemini дорабатывает карусель..."):
                    try:
                        raw, sources = generate_carousel(
                            project,
                            ctx["materials_text"],
                            ctx["mode"],
                            ctx["user_input"],
                            extra_task=ctx["extra_task"],
                            use_web_search=ctx["use_web_search"],
                            model=st.session_state.get("model_override") or None,
                            revision_of_slides=st.session_state.last_result,
                            revision_comment=revision_comment,
                        )
                        slides = parse_slides(raw)
                        st.session_state.last_result = slides
                        st.session_state.last_sources = sources

                        storage.add_history_entry(
                            project,
                            {
                                "mode": ctx["mode_label"],
                                "input_preview": f"[правка] {revision_comment.strip()[:180]}",
                                "slides": slides,
                                "sources": sources,
                            },
                        )

                        if remember_edit:
                            if storage.add_user_note(project, revision_comment):
                                st.success("Карусель доработана. Правка сохранена для проекта.")
                            else:
                                st.success("Карусель доработана.")
                        else:
                            st.success("Карусель доработана.")
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Непредвиденная ошибка: {e}")

# ---------- История ----------
with tab_history:
    history = project.get("history", [])
    if not history:
        st.caption("История генераций пуста.")
    for entry in history:
        title = f"{entry['created_at']} — {entry['mode']} — {entry['input_preview']}"
        with st.expander(title):
            for i, slide in enumerate(entry.get("slides", []), start=1):
                st.markdown(f"**Слайд {i}**")
                st.write(slide)
            if entry.get("sources"):
                st.markdown("**Источники**")
                for s in entry["sources"]:
                    st.caption(f"• [{s['title']}]({s['uri']})")
