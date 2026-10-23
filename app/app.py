"""Minimal Streamlit chat for the existing UAE law graph."""

from backend import load_graph, run_question, to_view_model

import streamlit as st

st.set_page_config(page_title="UAE Labour Law Assistant", page_icon="⚖️", layout="wide")


@st.cache_resource
def cached_graph():
    return load_graph()


st.title("⚖️ UAE Labour Law Assistant")
st.caption("Explains UAE Labour Law, its Executive Regulation, the 2022 amendment and the PDPL. "
           "For information only; this is not legal advice.")

# Load src early, before creating any chat jobs or importing other model libraries.
with st.spinner("Loading the law assistant…"):
    cached_graph()

if "messages" not in st.session_state:
    st.session_state.messages = []


def show_answer(view):
    st.markdown(view["answer"])
    st.caption(f"Confidence: {view['confidence']} · {view['seconds']:.1f}s")
    for source in view["sources"]:
        if source["cited"]:
            with st.expander(f"[S{source['n']}] {source['label']}"):
                st.write(source["text"])


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            show_answer(message["view"])
        else:
            st.write(message["content"])

if question := st.chat_input("Ask about UAE employment or personal data protection"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            with st.status("Looking up the law…", expanded=True) as status:
                for event in run_question(question):
                    if event.get("done"):
                        view = to_view_model(event["state"])
                        view["run_id"] = event["run_id"]
                    else:
                        st.write(f"✓ {event['node'].replace('_', ' ').capitalize()}")
                status.update(label="Complete", state="complete", expanded=False)
            show_answer(view)
            st.session_state.messages.append({"role": "assistant", "view": view})
        except Exception:
            st.error("The assistant could not complete this request. Please try again.")
