"""Opt-in checks that call the configured graph and submit one LangSmith rating.

Run from the repo root: .venv/bin/python tests/live_ui_smoke.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from backend import conversation_markdown
from streamlit.testing.v1 import AppTest


def main():
    app = AppTest.from_file(str(ROOT / 'app/app.py'), default_timeout=120).run()
    prompts = [
        'How many days of annual leave do I get?',
        'What does Article 51 say?',
        'Can my employer keep my passport?',
        'What is the fee for a UAE Golden Visa?',
        'How do I get a work permit?',
        'How can I get a golden visa?',
    ]
    for question in prompts:
        app.chat_input[0].set_value(question).run()
        assert not app.exception, [e.message for e in app.exception]
        view = app.session_state['messages'][-1]['view']
        assert view['question'] == question
        html = '\n'.join(e.proto.body for e in app.get('html'))
        if view['path'].startswith('answered'):
            cards = view['display_sources']
            assert [s['n'] for s in cards] == list(range(1, len(cards) + 1))
            assert cards and view['follow_ups']
            if view['confidence'] == 'Low':
                assert any('Weak match with the law text' in w.value for w in app.warning)
        if question == prompts[1]:
            cards = [s for s in view['display_sources'] if s['source'] == 'labour_law' and s['article'] == 51]
            assert len(cards) == 1
            assert len(cards[0]['parts']) >= 2, cards
        if question == prompts[3]:
            assert view['path'].startswith('refused')
            assert 'icp.gov.ae' in view['display_answer'] and 'gdrfad.gov.ae' in view['display_answer']
            assert 'No matching source' in html
        if question == prompts[4] and view['path'].startswith('refused'):
            assert 'mohre.gov.ae' in view['display_answer']
        print(question, '=>', view['path'], view['confidence'], 'cards:', len(view['display_sources']), 'exact trace:', view['run_id'] in view.get('trace_url', ''), flush=True)
    app.button(key='feedback_1_up').click().run()
    assert not app.exception
    assert app.session_state['feedback'][1]['saved'], 'Live LangSmith feedback was not saved'
    assert app.button(key='feedback_1_up').disabled and app.button(key='feedback_1_down').disabled
    assert any('Thanks — feedback saved' in e.proto.body for e in app.get('toast'))
    print('Live LangSmith feedback and toast passed', flush=True)
    export = conversation_markdown(app.session_state['messages'])
    assert all(question in export for question in prompts)
    assert '### Citations' in export and '[S1]' in export
    assert app.get('download_button')[0].proto.label == 'Download conversation'
    print('Conversation export passed', flush=True)
    app.button_group[0].set_value('How it was evaluated').run()
    assert not app.exception and app.get('vega_lite_chart')
    print('Evaluation chart passed', flush=True)


if __name__ == '__main__':
    main()
