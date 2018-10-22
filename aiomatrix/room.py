import asyncio


class Room:
    """Instance of a matrix room"""
    def __init__(self, session, api, event_manager, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias
        self.event_manager = event_manager

    async def send_message(self, message):
        """
        Sends a message to the room.
        :param message: Message string
        """
        await self.api.room_send_message(self.room_id, message)

    async def get_message(self):
        temp_queue = asyncio.Queue()
        await self.event_manager.add_customer("message", temp_queue, self.room_id)
        while True:
            try:
                room_id, sender, message = await temp_queue.get()
                yield room_id, sender, message
            except asyncio.CancelledError:
                await self.event_manager.remove_customer("message", temp_queue, room_id)

    async def get_typing(self):
        temp_queue = asyncio.Queue()
        await self.event_manager.add_customer("typing", temp_queue, self.room_id)

        while True:
            try:
                room_id, sender = await temp_queue.get()
                yield room_id, sender
            except asyncio.CancelledError:
                await self.event_manager.remove_customer("typing", temp_queue, room_id)
