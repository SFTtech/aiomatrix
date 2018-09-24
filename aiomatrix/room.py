from aiomatrix.eventManager import EventManager
import asyncio

class Room():
    def __init__(self, session, api, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias
        self.message_queue = asyncio.Queue(loop=asyncio.get_event_loop())
        self.typing_queue = asyncio.Queue(loop=asyncio.get_event_loop())
        self.sync_task = None
        self.sync_event_list = []
        self.event_manager = EventManager(self.room_id, self.api)

    async def send_message(self, message):
        await self.api.room_send_message(self.room_id, message)

    #region Listeners

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

    #endregion

    async def get_new_message(self):
        temp_queue = asyncio.Queue()
        await self.event_manager.add_customer("message", temp_queue)
        while True:
            try:
                room_id, sender, message = await temp_queue.get()
                yield room_id, sender, message
            except asyncio.CancelledError:
                await self.event_manager.remove_customer("message", temp_queue)

    async def get_typing(self):
        temp_queue = asyncio.Queue()
        await self.event_manager.add_customer("typing", temp_queue)

        while True:
            try:
                room_id, sender = await temp_queue.get()
                yield room_id, sender
            except asyncio.CancelledError:
                await self.event_manager.remove_customer("typing", temp_queue)

    async def __sync_task(self):
        # Remove old events (set since_token to now)
        resp_json = await self.api.sync()
        self.api.set_since_token(resp_json["next_batch"])
        # Start waiting for new events
        while True:

            #TODO beautify, also fix api.sync() to accept all events not just room internal
            if "message" in self.sync_event_list:
                timeline = "m.room.message"
            else:
                timeline = None
            if "typing" in self.sync_event_list:
                ephemeral = ['m.typing']
            else:
                ephemeral = None

            resp_json = await self.api.sync(filter_timeline_types=timeline, filter_ephemeral_types=ephemeral)
            self.api.set_since_token(resp_json["next_batch"])

            if self.room_id in resp_json['rooms']['join']:
                for event in resp_json['rooms']['join'][self.room_id]['timeline']['events']:
                    self.message_queue.put_nowait((self.room_id, event['sender'], event['content']['body']))

            if self.room_id in resp_json['rooms']['join']:
                for event in resp_json['rooms']['join'][self.room_id]['ephemeral']['events']:
                    # The 'and' part is added, because when one stops typing you receive an empty 'm.typing' event
                    if 'user_ids' in event['content'] and event['content']['user_ids']:
                        self.typing_queue.put_nowait((self.room_id, event['content']['user_ids']))