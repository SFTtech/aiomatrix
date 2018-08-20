
class Room():
    def __init__(self, session, api, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias

    async def send_message(self, message):
        await self.api.room_send_message(self.room_id, message)

    async def add_listener_receive_messages(self, callback):
        self.session.listen_room_messages.append({'room_id': self.room_id, 'callback': callback})
        #TODO: Filter, how to set?
        #self.session.set_filter('{ "rooms": { "join": {  } }')
        await self.session._start_sync()

    async def del_listener_receive_messages(self, callback=None):
        # TODO: One or multiple listeners per room allowed?
        # TODO: Either limit add_listener or loop in del_listener
        #self.session.listen_room_messages.remove({'room_id': self.room_id, 'callback': callback})
        for entry in self.session.listen_room_messages:
            if entry['room_id'] is self.room_id:
                self.session.listen_room_messages.remove(entry)

        await self.session._stop_sync()
