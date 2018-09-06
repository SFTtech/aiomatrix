
class Room():
    def __init__(self, session, api, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias

    async def send_message(self, message):
        await self.api.room_send_message(self.room_id, message)

    #TODO general methods to add/remove listeners (too much copy paste)
    async def add_listener_receive_messages(self, callback):
        self.session.listen_room_messages.append({'room_id': self.room_id, 'callback': callback})
        await self.session._start_sync()

    async def del_listener_receive_messages(self, callback=None):
        for entry in self.session.listen_room_messages:
            if entry['room_id'] is self.room_id:
                if not callback or entry['callback'] is callback:
                    self.session.listen_room_messages.remove(entry)

        await self.session._stop_sync()

    async def add_listener_typing(self, callback):
        self.session.listen_room_typing.append({'room_id': self.room_id, 'callback': callback})
        await self.session._start_sync()

    async def del_listener_typing(self, callback=None):
        for entry in self.session.listen_room_typing:
            if entry['room_id'] is self.room_id:
                if not callback or entry['callback'] is callback:
                    self.session.listen_room_typing.remove(entry)

        await self.session._stop_sync()

    async def add_listener_receipt(self, callback):
        self.session.listen_room_receipt.append({'room_id': self.room_id, 'callback': callback})
        await self.session._start_sync()

    async def del_listener_receipt(self, callback=None):
        for entry in self.session.listen_room_receipt:
            if entry['room_id'] is self.room_id:
                if not callback or entry['callback'] is callback:
                    self.session.listen_room_receipt.remove(entry)

        await self.session._stop_sync()

    async def get_new_message(self):
        #create taks, check if already run and if does corrrect stuff otherwise kill and restart
        while self.session.sync_flag:
            room_id, sender, message = await self.session.listen_queue.get()
            yield room_id, sender, message
