"""Qanoon: the presentation layer for the UAE law assistant."""

# Import backend first so model thread settings are established early.
from backend import (
    PIPELINE_LABELS, PIPELINE_NEXT_LABELS, SUGGESTIONS, answer_markdown, clipboard_html,
    highlighted_text, load_graph, run_question, to_view_model,
)

from html import escape
from pathlib import Path
from time import perf_counter

import streamlit as st

st.set_page_config(page_title="Qanoon — UAE Labour Law Assistant", page_icon="⚖️", layout="wide")


@st.cache_resource
def cached_graph():
    return load_graph()


for key, default in (("messages", []), ("feedback", {}), ("show_pipeline", True)):
    if key not in st.session_state:
        st.session_state[key] = default


with st.sidebar:
    st.markdown('<div class="sidebar-brand">⚖ &nbsp; Qanoon</div>', unsafe_allow_html=True)
    st.caption("A little clarity goes a long way.")
    st.markdown("### About")
    st.write("Answers grounded in four UAE laws, with article text you can check for yourself.")
    st.caption("Labour Law · Executive Regulation · 2022 Amendment · Personal Data Protection Law")
    st.markdown("### How it works")
    for icon, label, description in [
        ("↪", "Rewrite", "Understand the law’s vocabulary"),
        ("⌕", "Hybrid search", "Find relevant articles"),
        ("⇅", "Re-rank", "Bring the closest matches first"),
        ("◇", "Evidence gate", "Check for enough support"),
        ("§", "Cited answer", "Show the words behind the answer"),
    ]:
        st.markdown(f'<div class="pipeline-step"><span>{icon}</span><div><b>{label}</b><small>{description}</small></div></div>', unsafe_allow_html=True)
    st.markdown("### Settings")
    appearance = st.selectbox("Appearance", ["System", "Light", "Dark"])
    st.toggle("Show pipeline details", key="show_pipeline")
    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.feedback = {}
        st.session_state.pop("pending_question", None)
        st.session_state.pop("failed_question", None)
        st.rerun()
    st.markdown('<div class="sidebar-disclaimer">Explains the law; not legal advice.</div>', unsafe_allow_html=True)

css = (Path(__file__).with_name("style.css")).read_text()
theme_override = ""
if appearance != "System":
    palette = (
        "--bg:#f8f7f3;--card:#fff;--ink:#182b44;--muted:#637084;--line:#e3e5e8;"
        "--sand:#f1e9d9;--gold:#856426;--amber:#fff4d9;--amber-ink:#805517;--green:#e5f3ec;--green-ink:#24664b;"
        if appearance == "Light" else
        "--bg:#101b2b;--card:#19283c;--ink:#e8edf5;--muted:#a5b3c7;--line:#304056;"
        "--sand:#342f25;--gold:#d4b878;--amber:#382d1e;--amber-ink:#f0cc84;--green:#1c3b32;--green-ink:#9ed8be;"
    )
    theme_override = f".stApp {{{palette} color-scheme:{appearance.lower()};}}"
st.html(f"<style>{css}\n{theme_override}</style>")

st.html('''<div class="brand-bar"><div class="brand-mark">⚖</div><div>
    <div class="eyebrow">QANOON <span>قانون</span></div>
    <h1>UAE Labour Law Assistant</h1>
    <p>Understand your rights. See the source.</p></div></div>
    <div class="law-badges"><span>Labour Law · 33/2021</span><span>Executive Regulation · 1/2022</span>
    <span>2022 Amendment · 14/2022</span><span>PDPL · 45/2021</span></div>''')


def render_sources(view, message_id):
    cited = [source for source in view["sources"] if source["cited"]]
    sources = cited or view["sources"]
    st.html(f'<div class="section-label">{"CITED SOURCES" if cited else "RETRIEVED SOURCES · NO CITATIONS IN ANSWER"} <span>{len(sources):02}</span></div>')
    if not sources:
        st.caption("No source text was returned for this response.")
    for offset in range(0, len(sources), 2):
        columns = st.columns(2, gap="small")
        for column, source in zip(columns, sources[offset:offset + 2]):
            with column, st.container(border=True, key=f"source_{message_id}_{source['n']}"):
                st.html(f'''<div id="source-{message_id}-{source['n']}" class="source-heading">
                    <span class="source-number">S{source['n']}</span><b>{escape(source['label'])}</b></div>
                    <div class="law-title">{escape(source['law_title'])}</div>
                    <div class="source-meta"><span>Relevance {source['score']:.0%}</span>
                    <span>Part {source['part']} / {source['total_parts']}</span></div>
                    <div class="relevance-track"><div style="width:{source['score'] * 100:.1f}%"></div></div>''')
                with st.expander("Read article text"):
                    st.html('<div class="article-text">' + highlighted_text(source["text"], view.get("question", ""), view["rewritten"]) + '</div>')


def render_answer(view, index):
    message_id = str(index)
    refused = view["path"].startswith("refused")
    if refused:
        with st.container(border=True, key=f"refusal_{index}"):
            st.html('<div class="refusal-title">◇ &nbsp; Not covered by these laws</div>')
            st.markdown(view["answer"])
            st.caption("Try asking about leave, wages, gratuity, employment contracts or personal data protection.")
            st.markdown("[Visit MOHRE ↗](https://www.mohre.gov.ae/)")
    else:
        st.markdown(answer_markdown(view["answer"], message_id), unsafe_allow_html=True)
        if view["confidence"] == "Low":
            st.warning("Weak match with the law text — please verify the cited article.", icon="⚠️")
    level = view["confidence"].lower() if not refused else "unavailable"
    st.html(f'<div class="answer-meta"><span class="confidence {level}">{escape(view["confidence"])} confidence</span><span>{view["seconds"]:.1f}s response time</span></div>')
    with st.expander("Rewritten as", expanded=False):
        st.caption(view["rewritten"] or "No rewrite available.")
    if not refused:
        render_sources(view, message_id)
    if st.session_state.show_pipeline and view.get("timeline"):
        with st.expander("Pipeline details"):
            for step in view["timeline"]:
                st.caption(f"✓ {step['label']} · {step['seconds']:.1f}s")
    with st.container(key=f"actions_{index}"):
        copy_col, up_col, down_col, trace_col = st.columns([2, 1, 1, 2], gap="small")
        with copy_col:
            st.iframe(clipboard_html(view["answer"], appearance), height=40, alt="Copy answer")
        for column, value, label in [(up_col, "up", "👍"), (down_col, "down", "👎")]:
            with column:
                if st.button(label, key=f"feedback_{index}_{value}", help="Helpful" if value == "up" else "Needs improvement", type="primary" if st.session_state.feedback.get(index) == value else "secondary", use_container_width=True):
                    st.session_state.feedback[index] = value
                    st.rerun()
        with trace_col:
            st.link_button("View trace ↗", "https://smith.langchain.com", use_container_width=True)


selected = None
if not st.session_state.messages:
    st.html('''<section class="welcome"><div class="eyebrow">THE LAW, A LITTLE CLEARER</div>
        <h2>Good questions deserve<br>grounded answers.</h2>
        <p>Ask in everyday language. Explore the articles behind every answer.</p></section>
        <div class="section-label">WHERE WOULD YOU LIKE TO START?</div>''')
    for row in range(2):
        for column, (topic, question) in zip(st.columns(3, gap="small"), SUGGESTIONS[row * 3:row * 3 + 3]):
            with column, st.container(border=True, key=f"suggestion_{row}_{topic.replace(' ', '_')}"):
                st.html(f'<div class="topic-label">{escape(topic)}</div>')
                if st.button(question + "  ↗", key=f"suggest_{topic}", use_container_width=True):
                    selected = question
    st.html('<div class="welcome-note">ARTICLE-LEVEL SOURCES <span>·</span> FOUR UAE LAWS <span>·</span> PLAIN LANGUAGE</div>')

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"], avatar="⚖️" if message["role"] == "assistant" else "👤"):
        if message["role"] == "assistant":
            render_answer(message["view"], index)
        else:
            st.write(message["content"])

question = st.chat_input("Ask about leave, gratuity, contracts, your data…", disabled="pending_question" in st.session_state) or selected
if question:
    # Rerun once to remove the welcome cards before inserting the conversation.
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.pop("failed_question", None)
    st.session_state.pending_question = question
    st.rerun()

if pending := st.session_state.pop("pending_question", None):
    with st.chat_message("assistant", avatar="⚖️"):
        started = perf_counter()
        timeline = []
        try:
            with st.status("Understanding your question · 0.0s", expanded=st.session_state.show_pipeline) as status:
                cached_graph()
                view = None
                for event in run_question(pending):
                    elapsed = perf_counter() - started
                    if event.get("done"):
                        view = to_view_model(event["state"])
                        view.update(run_id=event["run_id"], timeline=timeline)
                    else:
                        label = PIPELINE_LABELS.get(event["node"], event["node"].capitalize())
                        timeline.append({"label": label, "seconds": elapsed})
                        st.write(f"✓ {label} · {elapsed:.1f}s")
                        next_label = PIPELINE_NEXT_LABELS.get(event["node"], label)
                        status.update(label=f"{next_label} · {elapsed:.1f}s")
                if view is None:
                    raise RuntimeError("No final graph state")
                status.update(label=f"{'Search complete' if view['path'].startswith('refused') else 'Answer ready'} · {view['seconds']:.1f}s", state="complete", expanded=False)
            st.session_state.messages.append({"role": "assistant", "view": view})
            st.rerun()
        except Exception:
            status.update(label="We couldn’t finish this search", state="error", expanded=False)
            st.session_state.failed_question = pending

if failed := st.session_state.get("failed_question"):
    st.error("We couldn’t complete your last question. Please try again in a moment.")
    if st.button("Try this question again"):
        st.session_state.pending_question = failed
        st.session_state.pop("failed_question", None)
        st.rerun()

st.caption("Explains the law; not legal advice. Always check the cited article for your situation.")
