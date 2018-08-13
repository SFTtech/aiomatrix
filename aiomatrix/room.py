import asyncio

from aiomatrix.lowlevel import AioMatrixApi

class Room():
    def __init__(self, api, room_id, room_alias = None):
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias

    async def send_message(self, message):

        response = await self.api.room_send_message(self.room_id, message)
