"""Compatibility entry point; orchestration lives in avatar.conversation."""
from ...conversation.engine import ConversationService

AvatarEngine = ConversationService
