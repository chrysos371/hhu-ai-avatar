"""Experiment-only binding; no CLI flag, server default or model prompt change."""
from ..main import Avatar
from ..brain.tasks import TaskTracker
from .body_review import review_explicit_body


class ExplicitBodyReviewAvatar(Avatar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.final_reply_reviewer = self._review_explicit_body

    def _review_explicit_body(self, user_text, reply):
        # Rebuild pure intent only from the current privacy-valid window.
        writing = TaskTracker()
        for message in self.memory.get_short_term():
            if message['role'] == 'user':
                writing.update(message['content'])
        result = review_explicit_body(reply,
            composition=writing.current is not None,
            fiction=self.boundaries.fiction and not self.boundaries.literary_analysis,
            role=self.speaker_scope.scope == 'fictional_character')
        return result.reply, {'reviewer': 'lab_explicit_body_v1', **result.metadata()}
