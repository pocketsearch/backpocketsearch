# Roadmap Model

class Roadmap:
    def __init__(self, title, description, status, deadline):
        self.title = title     # The title of the roadmap
        self.description = description # Detailed information about the roadmap
        self.status = status   # Status (e.g., ongoing, completed)
        self.deadline = deadline # Deadline if applicable
        self.tasks = []        # Task list related to the roadmap

# Task Model

class Task:
    def __init__(self, title, description, is_completed=False):
        self.title = title     # The task title
        self.description = description # Task details
        self.is_completed = is_completed # Completion status
