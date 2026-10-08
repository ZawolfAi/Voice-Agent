"""Small helpers for creating and updating conversation state."""

from voice_agent.app.schemas.requests import ConversationState
from voice_agent.app.schemas.auth import AuthenticatedUserContext


def new_conversation(
    authenticated_user: AuthenticatedUserContext | None = None,
) -> ConversationState:
    """Create state; identity must be supplied by an authenticated host."""
    return ConversationState(authenticated_user=authenticated_user)