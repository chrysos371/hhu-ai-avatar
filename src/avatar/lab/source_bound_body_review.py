"""Separate v2 experiment; v1 and production factories remain unchanged."""
from ..main import Avatar
from ..cancellation import Cancelled
from .body_review import BodyReview, review_explicit_body
from .composition_sources import CompositionSources


class SourceBoundBodyReviewAvatar(Avatar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.composition_sources = CompositionSources(self.memory)
        self.final_reply_reviewer = self._review_source_bound_body
        self._composition_observed = False
        self._composition_revision = self.memory.context_revision

    def respond(self, user_text, *args, **kwargs):
        self.memory.get_short_term()
        self._composition_revision = self.memory.context_revision
        previous = self._current_message_id
        self._composition_observed = False
        try:
            return super().respond(user_text, *args, **kwargs)
        finally:
            # Rule/cancelled turns still contain committed user speech. Parse
            # their control only; never replay a model, reminder or tool action.
            if (not self._composition_observed and self._current_message_id is not None
                    and self._current_message_id != previous):
                try:
                    self.composition_sources.observe(user_text, self._composition_revision, self._current_message_id)
                except Cancelled:
                    # A changed privacy version must not be rebuilt from old text.
                    pass

    def _review_source_bound_body(self, user_text, reply):
        self._composition_observed = True
        frame = self.composition_sources.observe(user_text, self._composition_revision, self._current_message_id)
        fiction = self.boundaries.fiction and not self.boundaries.literary_analysis
        role = self.speaker_scope.scope == 'fictional_character'
        deferred = frame.frame == 'unverified' and not (fiction or role)
        result = BodyReview(reply) if deferred else review_explicit_body(reply,
            composition=frame.frame == 'writing', fiction=fiction, role=role)
        sources = [frame.root_id] if frame.frame == 'writing' else []
        return result.reply, {'reviewer': 'lab_source_bound_body_v2', **result.metadata(),
            'review_deferred': deferred, 'composition_context': frame.metadata(), 'source_message_ids': sources}
