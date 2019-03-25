import json


class EventFilter:
    """Low level class. Takes care of creating the filter for event requests/sync.
    Can be used to parse and check the response JSON."""
    def __init__(self):
        self.timeline_types = []
        self.timeline_rooms = []
        self.ephemeral_types = []
        self.ephemeral_rooms = []

    def get_filter_dict(self):
        """
        Creates a filter/sync filter python dictionary.
        :return: Returns filter/sync filter python dictonary.
        """
        # Invite Events and Prekey (to device) events can't be filtered out
        event_filter = {
            "room": {
                "ephemeral": {
                    "types": self.ephemeral_types,
                    "rooms": self.__get_unique_list(self.ephemeral_rooms)
                },
                "timeline": {
                    "types": self.timeline_types,
                    "rooms": self.__get_unique_list(self.timeline_rooms)
                }
            }
        }

        return event_filter

    def get_filter_string(self):
        """
        Creates and returns the filter/sync filter python dictionary as a string.
        :return: Returns filter/sync filter python string.
        """
        return json.dumps(self.get_filter_dict())

    def set_filter(self, event, room_id):
        """
        Sets a filter event for a specific room. This event is added to the list
        of accepted events and correctly parsed for given responses.
        :param event: Event type, e.g. "message", "typing", ...
        :param room_id: Room ID of accepted event origins.
        """
        if event == "message":
            self.timeline_rooms.append((event, room_id))
            if "m.room.message" not in self.timeline_types:
                self.timeline_types.append("m.room.message")
        if event == "encryption":
            self.timeline_rooms.append((event, room_id))
            if "m.room.encryption" not in self.timeline_types:
                self.timeline_types.append("m.room.encryption")
        if event == "encrypted":
            self.timeline_rooms.append((event, room_id))
            if "m.room.encrypted" not in self.timeline_types:
                self.timeline_types.append("m.room.encrypted")
        if event == "typing":
            self.ephemeral_rooms.append((event, room_id))
            if "m.typing" not in self.ephemeral_types:
                self.ephemeral_types.append("m.typing")

    def remove_filter(self, event, room_id):
        """
        Removes a filter event for a specific room. The given event
        is no longer accepted and responses of this room are discarded.
        :param event: Event type, e.g. "message", "typing", ...
        :param room_id: Room ID of accepted event origins.
        """
        if event == "message":
            self.timeline_rooms.remove((event, room_id))
            # Check if other rooms still require the given event, otherwise remove entry
            if not [entry for entry in self.timeline_rooms if entry[0] == "message"]:
                self.timeline_types.remove("m.room.message")
        if event == "encryption":
            self.timeline_rooms.remove((event, room_id))
            # Check if other rooms still require the given event, otherwise remove entry
            if not [entry for entry in self.timeline_rooms if entry[0] == "encryption"]:
                self.timeline_types.remove("m.room.encryption")
        if event == "encrypted":
            self.timeline_rooms.remove((event, room_id))
            # Check if other rooms still require the given event, otherwise remove entry
            if not [entry for entry in self.timeline_rooms if entry[0] == "encrypted"]:
                self.timeline_types.remove("m.room.encrypted")
        if event == "typing":
            self.ephemeral_rooms.remove((event, room_id))
            # Check if other rooms still require the given event, otherwise remove entry
            if not [entry for entry in self.ephemeral_rooms if entry[0] == "typing"]:
                self.ephemeral_types.remove("m.room.typing")

    @staticmethod
    def __get_unique_list(rooms):
        """
        Used to create a list of unique room IDs out of a list of [(event,room_id),..].
        The result can be used to create the room filter.
        :param rooms: List of tuples: [(event,room_id1), (event,room_id1), (event,room_id2)..]
        :return: List of unique rooms [ room_id1, room_id2, ... ]
        """
        return list(set(room_id for event, room_id in rooms))

    def get_filtered_event(self, resp_json):
        """
        Takes a JSON response of the sync method. Filters and returns the corresponding
        interesting information depending on the accepted origins of the events.
        :param resp_json: JSON format sync method response
        :return: List of tuples containing the relevant event-dependent information. Empty list if the given
        JSON string does not consist of accepted information.
        """
        event_list = list()

        for room_id in self.__get_unique_list(self.timeline_rooms):
            if room_id in resp_json['rooms']['join']:
                for event in resp_json['rooms']['join'][room_id]['timeline']['events']:
                    if event['type'] == "m.room.message":
                        event_list.append(({"message"}, room_id, event['sender'], event['content']['body']))
                    if event['type'] == "m.room.encryption":
                        event_list.append(({"encryption"}, room_id, event['sender'], event['content']['algorithm']))
                    if event['type'] == "m.room.encrypted":
                        event_list.append(({"encrypted"}, room_id, event['sender'], event['content']['ciphertext'],
                                           event['content']['device_id'], event['content']['session_id']))

        for room_id in self.__get_unique_list(self.ephemeral_rooms):
            if room_id in resp_json['rooms']['join']:
                for event in resp_json['rooms']['join'][room_id]['ephemeral']['events']:
                    # The 'and' part is added, because when one stops
                    # typing you receive an empty 'm.typing' event
                    if 'user_ids' in event['content'] and event['content']['user_ids']:
                        event_list.append(({"typing"}, room_id, event['content']['user_ids']))

        if resp_json['rooms']['invite']:
            for key in resp_json['rooms']['invite']:
                for event in resp_json['rooms']['invite'][key]['invite_state']['events']:
                    if 'name' in event['content']:
                        event_list.append(({"invite"}, key, event['content']['name'], event['sender']))

        if resp_json['to_device']:
            for event in resp_json['to_device']['events']:
                if event['type'] == 'm.room.encrypted':
                    event_list.append(({"prekey"}, None, event['sender'], event['content']))

        if resp_json['device_one_time_keys_count']:
            event_list.append(({"otk"}, resp_json['device_one_time_keys_count']['signed_curve25519']))

        return event_list
