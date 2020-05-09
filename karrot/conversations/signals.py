from django.dispatch import Signal

conversation_marked_seen = Signal(providing_args=['participant'])
thread_marked_seen = Signal(providing_args=['participant'])
new_conversation_message = Signal(providing_args=['message'])
new_thread_message = Signal(providing_args=['message'])
