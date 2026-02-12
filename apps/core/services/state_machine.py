"""Conversation state machine engine."""

import logging

logger = logging.getLogger(__name__)

FLOW_DEFINITIONS = {
    "clarification": {
        "initial": {"on_send": "awaiting_response"},
        "awaiting_response": {"on_reply": "processing", "on_timeout": "timed_out"},
        "processing": {"on_complete": "completed", "on_followup": "awaiting_response"},
        "timed_out": {},
        "completed": {},
    },
    "digest": {
        "initial": {"on_send": "awaiting_review"},
        "awaiting_review": {"on_reply": "processing", "on_timeout": "timed_out"},
        "processing": {"on_complete": "completed"},
        "timed_out": {},
        "completed": {},
    },
    "reminder": {
        "initial": {"on_send": "notified"},
        "notified": {"on_reply": "acknowledged"},
        "acknowledged": {},
    },
    "monthly_call_defer": {
        "initial": {"on_send": "notified"},
        "notified": {},
    },
    "accountant_digest": {
        "initial": {"on_send": "awaiting_action"},
        "awaiting_action": {"on_reply": "processing", "on_timeout": "expired"},
        "processing": {"on_complete": "completed"},
        "expired": {},
        "completed": {},
    },
    "weekly_batch": {
        "initial": {"on_send": "awaiting_responses"},
        "awaiting_responses": {"on_reply": "processing", "on_timeout": "timed_out"},
        "processing": {"on_complete": "completed", "on_followup": "awaiting_responses"},
        "timed_out": {},
        "completed": {},
    },
}


class StateMachine:
    """Drive conversation state transitions."""

    def transition(self, conversation, event: str) -> str | None:
        """Attempt a state transition. Returns new state or None if invalid."""
        flow = FLOW_DEFINITIONS.get(conversation.context_type, {})
        current_transitions = flow.get(conversation.current_state, {})
        new_state = current_transitions.get(event)

        if new_state is None:
            logger.warning(
                "Invalid transition: conversation=%s flow=%s state=%s event=%s",
                conversation.id,
                conversation.context_type,
                conversation.current_state,
                event,
            )
            return None

        old_state = conversation.current_state
        conversation.current_state = new_state

        # Update conversation status based on state
        if new_state in ("timed_out", "expired"):
            conversation.status = "timed_out"
        elif new_state == "completed":
            conversation.status = "completed"
        elif new_state in ("awaiting_response", "awaiting_review", "awaiting_action", "awaiting_responses"):
            conversation.status = "waiting_reply"

        conversation.save(update_fields=["current_state", "status", "updated_at"])
        logger.info(
            "State transition: conversation=%s %s -> %s (event=%s)",
            conversation.id,
            old_state,
            new_state,
            event,
        )
        return new_state

    def get_available_events(self, conversation) -> list[str]:
        """Get available events for current state."""
        flow = FLOW_DEFINITIONS.get(conversation.context_type, {})
        return list(flow.get(conversation.current_state, {}).keys())
