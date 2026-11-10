"""Character budgets: retain whole data items/messages, never slice safety prompts."""
import json


class ContextBudget:
    history_chars = 4000
    system_chars = 16000

    def items(self, values, limit):
        result = []
        for value in values:
            candidate = result + [value]
            if len(json.dumps(candidate, ensure_ascii=False)) <= limit:
                result.append(value)
        return result

    def data(self, profile, facts, reminders, summary):
        profile_items = self.items(list(profile.items()), 1000)
        return (dict(profile_items), self.items(facts, 2400),
                self.items(reminders, 1200), self.items(summary, 1600))

    def history(self, messages, limit=None):
        remaining = self.history_chars if limit is None else limit
        result = []
        for message in reversed(messages):
            size = len(message['content'])
            if size > remaining:
                break  # Keep a contiguous suffix; never stitch around a missing turn.
            result.append(message)
            remaining -= size
        return list(reversed(result))
