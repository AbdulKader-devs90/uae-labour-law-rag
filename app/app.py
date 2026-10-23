"""Qanoon: the presentation layer for the UAE law assistant."""

# Import backend first so model thread settings are established early.
from backend import (
    PIPELINE_LABELS, PIPELINE_NEXT_LABELS, SUGGESTIONS, answer_markdown, clipboard_html,
    highlighted_text, load_graph, run_question, to_view_model,
    METRIC_DEFINITIONS, VERSION_DEFINITIONS, VERSION_LABELS, conversation_markdown,
    load_evaluation, submit_feedback, trace_url,
)

from html import escape
from pathlib import Path
from time import perf_counter

import streamlit as st

st.set_option("client.showErrorDetails", "none")
st.set_page_config(page_title="Qanoon — UAE Labour Law Assistant", page_icon="⚖️", layout="wide")


@st.cache_resource(show_spinner="Loading legal models… ~10 s")
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
    st.download_button("Download conversation", data=conversation_markdown(st.session_state.messages), file_name="qanoon-conversation.md", mime="text/markdown", disabled=not st.session_state.messages, width="stretch", on_click="ignore")
    if st.button("Clear chat", width="stretch"):
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

if "feedback_notice" in st.session_state:
    if st.session_state.pop("feedback_notice"):
        st.toast("Thanks — feedback saved", icon="✅")
    else:
        st.toast("Feedback could not be saved to LangSmith. Your rating is kept in this session.", icon="⚠️")

st.html('''<div class="brand-bar"><div class="brand-mark">⚖</div><div>
    <div class="eyebrow">QANOON <span>قانون</span></div>
    <h1>UAE Labour Law Assistant</h1>
    <p>Understand your rights. See the source.</p></div></div>
    <div class="law-badges"><span>Labour Law · 33/2021</span><span>Executive Regulation · 1/2022</span>
    <span>2022 Amendment · 14/2022</span><span>PDPL · 45/2021</span></div>''')


def render_sources(view, message_id):
    sources = view['display_sources']
    cited = any(source['cited'] for source in sources)
    st.html(f'<div class="section-label">{"CITED SOURCES" if cited else "RETRIEVED SOURCES · NO CITATIONS IN ANSWER"} <span>{len(sources):02}</span></div>')
    if not sources:
        st.caption('No source text was returned for this response.')
    for offset in range(0, len(sources), 2):
        columns = st.columns(2, gap='small')
        for column, source in zip(columns, sources[offset:offset + 2]):
            with column, st.container(border=True, key=f"source_{message_id}_{source['n']}"):
                st.html(f'''<div id="source-{message_id}-{source['n']}" class="source-heading">
                    <span class="source-number">S{source['n']}</span><b>{escape(source['label'])}</b></div>
                    <div class="law-title">{escape(source['law_title'])}</div>
                    <div class="source-meta"><span>Relevance {source['score']:.0%}</span>
                    <span>{escape(source['part_label'])}</span></div>
                    <div class="relevance-track"><div style="width:{source['score'] * 100:.1f}%"></div></div>''')
                with st.expander('Read article text'):
                    for chunk in source['parts']:
                        if len(source['parts']) > 1:
                            st.caption(f"Part {chunk['part']} · {'cited' if chunk['cited'] else 'also retrieved'}")
                        st.html('<div class="article-text">' + highlighted_text(chunk['text'], view.get('question', ''), view['rewritten']) + '</div>')


def render_inspector(view):
    with st.expander('Pipeline details'):
        st.caption('Rewritten query')
        st.write(view['rewritten'] or 'No rewrite available.')
        st.html(f'''<div class="score-inspector"><div class="source-meta">
            <span>Top re-rank score <b>{view['top_score']:.3f}</b></span><span>Cut-off 0.10</span></div>
            <div class="score-track"><div style="width:{min(1, max(0, view['top_score'])) * 100:.1f}%"></div>
            <i title="Cut-off 0.10"></i></div></div>''')
        st.caption(f"Generate attempts: {view.get('attempts', 0)} · Path: {view['path']}")
        st.markdown('**All retrieved chunks**')
        if not view['sources']:
            st.caption('No chunks passed the evidence cut-off.')
        for source in view['sources']:
            with st.expander(f"Original S{source['n']} · {source['label']} · part {source['part']} · {source['score']:.3f}"):
                st.caption(f"Chunk: {source['chunk_id']} · {'Cited' if source['cited'] else 'Not cited'}")
                st.html('<div class="article-text">' + highlighted_text(source['text'], view['question'], view['rewritten']) + '</div>')
        for step in view.get('timeline', []):
            st.caption(f"✓ {step['label']} · {step['seconds']:.1f}s")


def render_answer(view, index):
    selected = None
    message_id = str(index)
    refused = view['path'].startswith('refused')
    if refused:
        with st.container(border=True, key=f'refusal_{index}'):
            st.html('<div class="refusal-title">◇ &nbsp; Not covered by these laws</div>')
            st.markdown(view['display_answer'])
            st.caption('Try asking about leave, wages, gratuity, employment contracts or personal data protection.')
    else:
        st.markdown(answer_markdown(view['display_answer'], message_id), unsafe_allow_html=True)
        if view['confidence'] == 'Low':
            st.warning('Weak match with the law text — please verify the cited article.', icon='⚠️')
    level = view['confidence'].lower() if not refused else 'unavailable'
    pill = 'No matching source' if refused else view['confidence'] + ' confidence'
    st.html(f'<div class="answer-meta"><span class="confidence {level}">{escape(pill)}</span><span>{view["seconds"]:.1f}s response time</span></div>')
    with st.expander('Rewritten as', expanded=False):
        st.caption(view['rewritten'] or 'No rewrite available.')
    if not refused:
        render_sources(view, message_id)
    if st.session_state.show_pipeline:
        render_inspector(view)
    with st.container(key=f'actions_{index}'):
        copy_col, up_col, down_col, trace_col = st.columns([2, 1, 1, 2], gap='small')
        with copy_col:
            st.iframe(clipboard_html(view['display_answer'], appearance), height=40, alt='Copy answer')
        rating = st.session_state.feedback.get(index)
        for column, score, label in [(up_col, 1, '👍'), (down_col, 0, '👎')]:
            with column:
                if st.button(label, key=f"feedback_{index}_{'up' if score else 'down'}", help='Helpful' if score else 'Needs improvement', disabled=rating is not None, type='primary' if rating and rating['score'] == score else 'secondary', width="stretch"):
                    saved = submit_feedback(view.get('run_id', ''), score)
                    st.session_state.feedback[index] = {'score': score, 'saved': saved}
                    st.session_state.feedback_notice = saved
                    st.rerun()
        with trace_col:
            st.link_button('View trace ↗', view.get('trace_url', 'https://smith.langchain.com'), width="stretch")
    if view.get('follow_ups'):
        st.html('<div class="section-label">KEEP EXPLORING</div>')
        with st.container(key=f'followups_{index}'):
            for n, suggestion in enumerate(view['follow_ups']):
                if st.button(suggestion, key=f'followup_{index}_{n}', width="content"):
                    selected = suggestion
    return selected


def render_evaluation():
    import altair as alt

    st.html('<section class="evaluation-intro"><div class="eyebrow">MEASURED, NOT ASSUMED</div><h2>How it was evaluated</h2><p>Three retrieval pipelines. Five checks on answer quality.</p></section>')
    try:
        evaluation = load_evaluation()
    except (ValueError, OSError):
        st.warning('The evaluation summary could not be read. Please check data/eval/final_summary.csv.')
        return
    if not evaluation['records']:
        st.info('Evaluation results are not available yet. Add data/eval/final_summary.csv to see the comparison.')
        return
    if evaluation['highlight']:
        st.html('<div class="evaluation-highlight">' + escape(evaluation['highlight']) + '</div>')
    st.caption(evaluation['note'])
    for definition in VERSION_DEFINITIONS.values():
        st.write(definition)
    st.caption('C final (3 runs) = C with the corrected gold set, averaged over three runs.')
    dark = appearance == 'Dark'
    ink = '#a5b3c7' if dark else '#637084'
    grid = '#304056' if dark else '#e3e5e8'
    chart = alt.Chart(alt.Data(values=evaluation['records'])).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X('metric:N', title=None, sort=list(METRIC_DEFINITIONS), axis=alt.Axis(labelAngle=-20, labelLimit=160)),
        xOffset=alt.XOffset('version:N', sort=list(VERSION_LABELS.values())),
        y=alt.Y('score:Q', title='Score', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format='.0%')),
        color=alt.Color('version:N', title=None, scale=alt.Scale(domain=list(VERSION_LABELS.values()), range=['#a5afbf', '#56789f', '#5e927b', '#b39352']), legend=alt.Legend(orient='top')),
        tooltip=[alt.Tooltip('version:N', title='Version'), alt.Tooltip('metric:N', title='Metric'), alt.Tooltip('score:Q', title='Score', format='.1%')],
    ).properties(height=320).configure(background='transparent').configure_view(strokeWidth=0).configure_axis(labelColor=ink, titleColor=ink, gridColor=grid, domain=False, ticks=False, labelFont='Inter', titleFont='Inter').configure_legend(labelColor=ink, labelFont='Inter')
    st.altair_chart(chart, width="stretch", theme=None)
    with st.container(border=True):
        for metric, definition in METRIC_DEFINITIONS.items():
            st.markdown(f'**{metric}** — {definition}')
    st.caption('Retrieval and citation metrics apply to questions with expected articles; blank evaluations are excluded from their means. Results describe this evaluation set, not a guarantee for every question.')


def render_error():
    with st.container(border=True, key="error_search"):
        st.error("We couldn’t reach the legal assistant. Please try again in a moment.")
        st.caption("Your question is saved. You can retry without typing it again.")
        if st.button("Try again"):
            if failed := st.session_state.pop("failed_question", None):
                st.session_state.pending_question = failed
            st.session_state.pop("model_load_failed", None)
            st.rerun()


page = st.segmented_control("Explore", ["Ask Qanoon", "How it was evaluated"], default="Ask Qanoon", key="page", label_visibility="collapsed")
if page == "How it was evaluated":
    render_evaluation()
    st.caption("Explains the law; not legal advice.")
    st.stop()

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
                if st.button(question + "  ↗", key=f"suggest_{topic}", width="stretch"):
                    selected = question
    st.html('<div class="welcome-note">ARTICLE-LEVEL SOURCES <span>·</span> FOUR UAE LAWS <span>·</span> PLAIN LANGUAGE</div>')

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"], avatar="⚖️" if message["role"] == "assistant" else "👤"):
        if message["role"] == "assistant":
            selected = render_answer(message["view"], index) or selected
        else:
            st.write(message["content"])

# Paint the welcome page before the first cached model load.
if not st.session_state.messages:
    try:
        cached_graph()
        st.session_state.pop("model_load_failed", None)
    except Exception:
        st.session_state.model_load_failed = True
    if st.session_state.get("model_load_failed"):
        render_error()

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
                        view["trace_url"] = trace_url(event["run_id"])
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

if st.session_state.get("failed_question"):
    render_error()

st.caption("Explains the law; not legal advice. Always check the cited article for your situation.")
