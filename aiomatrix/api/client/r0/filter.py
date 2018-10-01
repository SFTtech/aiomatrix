import json

class EventFilter:
    def __init__(self):
        self.timeline = []
        self.ephemeral = []


    def get_filter_dict(self):
        filter = \
        {"room":
            {
            "timeline":
                {
                    "types": self.timeline
                },
            "ephemeral":
                {
                    "types": self.ephemeral
                }
            }
        }
        return filter

    def get_filter_string(self):
        return json.dumps(self.get_filter_dict())

    def set_filter_message(self, message: bool = True):
        if message and "m.room.message" not in self.timeline:
            self.timeline.append("m.room.message")
        if not message:
            self.timeline.remove("m.room.message")

    def set_filter_typing(self, typing: bool = True):
        if typing and "m.typing" not in self.ephemeral:
            self.ephemeral.append("m.typing")
        if not typing:
            self.ephemeral.remove("m.typing")

    def set_filter_receipt(self, receipt: bool = True):
        if receipt and "m.receipt" not in self.ephemeral:
            self.ephemeral.append("m.receipt")
        if not receipt:
            self.ephemeral.remove("m.receipt")