# session_manager.py
import uuid

session_id = str(uuid.uuid4())  # Generate once and share

def get_session_id():
    return session_id