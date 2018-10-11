import asyncio

class Room():
    def __init__(self, session, api, event_manager, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias
        self.event_manager = event_manager

    async def send_message(self, message):
        await self.api.room_send_message(self.room_id, message)

    #TODO rename to get_message()
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
