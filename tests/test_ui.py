"""Offline regression checks for source visibility and confidence presentation.

Run: .venv/bin/python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from backend import (
    answer_markdown, clipboard_html, highlighted_text, to_view_model,
    refusal_guidance, conversation_markdown, load_evaluation, submit_feedback,
)
from streamlit.testing.v1 import AppTest


def sample_state(score=0.9, path='answered', answer='Annual leave is covered. [S1]'):
    document = SimpleNamespace(
        metadata={'source': 'labour_law', 'title': 'UAE Labour Law', 'article': 29, 'part': 1},
        page_content='[Labour Law — Article 29]\nAnnual leave <exact text>.',
    )
    return {'question': 'annual leave', 'answer': answer, 'results': [(document, score)],
            'top_score': score, 'path': path, 'rewritten': 'annual leave entitlement', 'seconds': 1.2}


def rendered_html(app):
    return '\n'.join(element.proto.body for element in app.get('html'))


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        # Offline UI checks never initialize real model libraries or call APIs.
        patcher = patch('backend.load_graph', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def render(self, state):
        app = AppTest.from_file(str(ROOT / 'app/app.py'))
        app.session_state['messages'] = [{'role': 'assistant', 'view': to_view_model(state)}]
        app.run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        return app

    def test_confidence_boundaries_and_refusal_override(self):
        for score, expected in [(0.8, 'High'), (0.799, 'Medium'), (0.3, 'Medium'), (0.299, 'Low')]:
            with self.subTest(score=score):
                self.assertEqual(to_view_model(sample_state(score))['confidence'], expected)
        self.assertEqual(to_view_model(sample_state(path='refused_by_llm'))['confidence'], '—')

    def test_low_warning_and_sources_always_visible(self):
        app = self.render(sample_state(0.2))
        self.assertIn('Weak match with the law text — please verify the cited article.', [w.value for w in app.warning])
        body = rendered_html(app)
        self.assertIn('Low confidence', body)
        self.assertIn('source-heading', body)
        self.assertIn('Part 1 / 2', body)
        self.assertIn('<mark>Annual</mark>', body)
        self.assertIn('&lt;exact text&gt;', body)
        app.toggle[0].set_value(False).run()
        self.assertIn('Low confidence', rendered_html(app))
        self.assertIn('source-heading', rendered_html(app))

    def test_uncited_answer_still_shows_retrieved_source_cards(self):
        app = self.render(sample_state(path='answered_no_citation', answer='Annual leave is covered.'))
        self.assertIn('RETRIEVED SOURCES', rendered_html(app))
        self.assertIn('source-heading', rendered_html(app))
        self.assertIn('High confidence', rendered_html(app))

    def test_refusal_has_guidance(self):
        app = self.render(sample_state(path='refused_low_score', answer="I couldn't find this in the laws I cover."))
        self.assertIn('Not covered by these laws', rendered_html(app))
        self.assertTrue(any('https://u.ae' in item.value for item in app.markdown))
        self.assertIn('No matching source', rendered_html(app))
        self.assertNotIn('— confidence', rendered_html(app))

    def test_suggestion_error_can_be_retried(self):
        app = AppTest.from_file(str(ROOT / 'app/app.py')).run()
        with patch('backend.load_graph', return_value=None), patch('backend.run_question', side_effect=RuntimeError('Unavailable')):
            app.button(key='suggest_Leave').click().run()
            self.assertTrue(app.error)
            self.assertEqual(app.session_state['failed_question'], 'How many days of annual leave do I get?')
            next(button for button in app.button if button.label == 'Try again').click().run()
            self.assertTrue(app.error)
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state['messages']), 1)

    def test_retry_resends_same_question_after_service_recovers(self):
        app = AppTest.from_file(str(ROOT / 'app/app.py')).run()
        question = 'How many days of annual leave do I get?'
        with patch('backend.run_question', side_effect=RuntimeError('private API error')):
            app.chat_input[0].set_value(question).run()
        self.assertFalse(app.exception)
        self.assertNotIn('private API error', str([e.value for e in app.error]))
        state = sample_state()
        state['question'] = question
        with patch('backend.run_question', return_value=iter([{'done': True, 'state': state, 'run_id': 'test'}])) as run, patch('backend.trace_url', return_value='https://smith.langchain.com'):
            next(button for button in app.button if button.label == 'Try again').click().run()
        run.assert_called_once_with(question)
        self.assertFalse(app.exception)
        self.assertEqual([m['role'] for m in app.session_state['messages']], ['user', 'assistant'])
        self.assertFalse(app.error)

    def test_markup_and_clipboard_escape_untrusted_html(self):
        self.assertIn('href="#source-1-2"', answer_markdown('Text [S2]', '1'))
        self.assertNotIn('<script>', answer_markdown('<script>alert(1)</script>', '1'))
        self.assertEqual(highlighted_text('leave <img>', 'leave'), '<mark>leave</mark> &lt;img&gt;')
        self.assertNotIn('</script><script>alert', clipboard_html('</script><script>alert(1)</script>'))

    def test_sparse_citations_are_renumbered_and_parts_merged(self):
        state = sample_state(answer='Gratuity [S3][S4]. Other [S2].')
        doc, _ = state['results'][0]
        part1 = SimpleNamespace(metadata={**doc.metadata, 'article': 51, 'part': 1}, page_content='[header]\nFirst gratuity part')
        part2 = SimpleNamespace(metadata={**doc.metadata, 'article': 51, 'part': 2}, page_content='[header]\nSecond gratuity part')
        state['results'] = [(doc, 0.9), (doc, 0.6), (part2, 0.7), (part1, 0.8)]
        view = to_view_model(state)
        self.assertEqual(view['answer'], state['answer'])
        self.assertEqual(view['display_answer'], 'Gratuity [S2]. Other [S1].')
        self.assertEqual([s['n'] for s in view['display_sources']], [1, 2])
        card = view['display_sources'][1]
        self.assertIn('parts 1–2', card['label'])
        self.assertEqual(card['score'], 0.8)
        self.assertEqual([p['part'] for p in card['parts']], [1, 2])
        self.assertEqual(len(view['sources']), 4)
        state['answer'] = 'Gratuity [S3][S4].'
        view = to_view_model(state)
        self.assertEqual(view['display_answer'], 'Gratuity [S1].')
        self.assertEqual(len(view['display_sources']), 1)
        self.assertTrue(any('deduct' in q for q in view['follow_ups']))

    def test_authority_routes_match_words(self):
        for question, domain in [('Golden Visa fee', 'icp.gov.ae'), ('How do I get a work permit?', 'mohre.gov.ae'), ('What about wages and WPS?', 'mohre.gov.ae'), ('Other topic', 'u.ae'), ('Is this advisable?', 'u.ae')]:
            self.assertIn(domain, refusal_guidance(question)['markdown'])
        self.assertIn('gdrfad.gov.ae', refusal_guidance('residency')['markdown'])

    def test_inspector_and_export_keep_consistent_citations(self):
        state = sample_state(answer='Annual leave [S2].')
        state['results'] *= 2
        state['attempts'] = 2
        app = self.render(state)
        body = rendered_html(app)
        self.assertIn('Cut-off 0.10', body)
        self.assertTrue(any('Generate attempts: 2' in e.value for e in app.caption))
        self.assertTrue(any('Original S1' in e.label for e in app.expander))
        self.assertTrue(any('Original S2' in e.label for e in app.expander))
        markdown = conversation_markdown([{'role': 'user', 'content': state['question']}, {'role': 'assistant', 'view': to_view_model(state)}])
        self.assertIn('Annual leave [S1].', markdown)
        self.assertIn('[S1] Labour Law · Art. 29', markdown)
        self.assertNotIn('[S2]', markdown)
        self.assertEqual(app.get('download_button')[0].proto.label, 'Download conversation')

    def test_feedback_success_and_failure_disable_both_buttons(self):
        for saved in [True, False]:
            app = self.render(sample_state())
            app.session_state['messages'][0]['view']['run_id'] = '12345678-1234-1234-1234-123456789012'
            with patch('backend.submit_feedback', return_value=saved) as submit:
                app.button(key='feedback_0_up').click().run()
                submit.assert_called_once_with('12345678-1234-1234-1234-123456789012', 1)
            self.assertTrue(app.button(key='feedback_0_up').disabled)
            self.assertTrue(app.button(key='feedback_0_down').disabled)
            self.assertTrue(app.get('toast'))
            self.assertFalse(app.exception)
        with patch('langsmith.Client') as client:
            self.assertTrue(submit_feedback('12345678-1234-1234-1234-123456789012', 0))
            client.return_value.create_feedback.assert_called_once_with(run_id='12345678-1234-1234-1234-123456789012', key='user_rating', score=0)
            client.return_value.create_feedback.side_effect = RuntimeError('service unavailable')
            self.assertFalse(submit_feedback('12345678-1234-1234-1234-123456789012', 1))

    def test_followup_click_sends_question_without_other_llm_calls(self):
        app = self.render(sample_state())
        followup = app.session_state['messages'][0]['view']['follow_ups'][0]
        def events(question):
            state = sample_state()
            state['question'] = question
            yield {'done': True, 'state': state, 'run_id': 'test'}
        with patch('backend.load_graph', return_value=None), patch('backend.run_question', side_effect=events) as run, patch('backend.trace_url', return_value='https://smith.langchain.com'):
            app.button(key='followup_0_0').click().run()
            run.assert_called_once_with(followup)
        self.assertEqual(app.session_state['messages'][-2]['content'], followup)
        self.assertFalse(app.exception)

    def test_evaluation_chart_uses_csv_values(self):
        import json
        import tempfile

        evaluation = load_evaluation()
        self.assertEqual({row['version'] for row in evaluation['records']}, {'A_naive', 'B_hybrid', 'C_full', 'C final (3 runs)'})
        self.assertEqual(len(evaluation['records']), 20)
        self.assertIn('100% correct decisions, retrieval and correctness', evaluation['highlight'])
        self.assertIn('93% faithfulness', evaluation['highlight'])
        app = AppTest.from_file(str(ROOT / 'app/app.py')).run()
        app.button_group[0].set_value('How it was evaluated').run()
        self.assertFalse(app.exception)
        chart = json.loads(app.get('vega_lite_chart')[0].proto.spec)
        self.assertEqual(chart['mark']['type'], 'bar')
        self.assertEqual(chart['encoding']['xOffset']['field'], 'version')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'v2').mkdir()
            (base / 'v2/summary.csv').write_text(',decision_correct\nA_naive,0.99\n')
            (base / 'final_summary.csv').write_text('version,runs,decision_correct,retrieval_hit,citation_hit,correctness,faithfulness,avg_seconds\nA_naive,1,0.4,0.5,0.6,0.7,0.8,1.2\n')
            values = load_evaluation(base)
            self.assertEqual(values['versions']['A_naive']['decision_correct'], 0.4)
            self.assertIsNone(values['highlight'])
            (base / 'final_summary.csv').unlink()
            self.assertFalse(load_evaluation(base)['records'])


if __name__ == '__main__':
    unittest.main()
