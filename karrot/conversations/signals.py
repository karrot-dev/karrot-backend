from django.dispatch import Signal

conversation_marked_seen = Signal()
thread_marked_seen = Signal()
new_conversation_message = Signal()
new_thread_message = Signal()
