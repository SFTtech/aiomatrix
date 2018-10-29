import asyncio


class Room:
    """Instance of a matrix room"""
    def __init__(self, session, api, event_manager, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias
        self.event_manager = event_manager

    async def invite_user(self, user_id):
        """
        Invites a user to join this room.
        :param user_id: User id e.g. @example:matrix.org
        """
        await self.api.room_invite(self.room_id, user_id)

    async def leave(self):
        """
        Leave the room. It is no longer possible to get message, typing, etc. events of this room.
        """
        await self.api.room_leave(self.room_id)

    async def send_message(self, message):
        """
        Sends a message to the room.
        :param message: Message string
        """
        await self.api.room_send_message(self.room_id, message)

    async def set_name(self, name):
        """
        Sets the displayed room name.
        :param name: New name of the room.
        """
        await self.api.room_set_name(self.room_id, name)

    async def set_topic(self, topic):
        """
        Sets the topic, extra information, short description of the room.
        :param topic: Room topic.
        """
        await self.api.room_set_topic(self.room_id, topic)

    async def get_members(self):
        """
        Returns a list of room members as user IDs (@example:matrix.org)
        :return: List of room members.
        """
        return await self.api.room_get_members(self.room_id)

    async def get_message(self):
        """
        Yields room message events whenever they occur.
        :return: RoomID, Sender, Message
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("message", temp_queue, self.room_id)
        while True:
            try:
                room_id, sender, message = await temp_queue.get()
                yield room_id, sender, message
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("message", temp_queue, room_id)

    async def get_typing(self):
        """
        Yields room typing events whenever they occur.
        :return: RoomID, Sender
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("typing", temp_queue, self.room_id)

        while True:
            try:
                room_id, sender = await temp_queue.get()
                yield room_id, sender
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("typing", temp_queue, room_id)
