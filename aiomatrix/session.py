import asyncio
import logging

from aiomatrix.room import Room
from aiomatrix.eventManager import EventManager
from .api import client

class Session:
    """Creates a personalized connection to a matrix server."""
    def __init__(self, username, password, base_url, device_id=None, log_level=20):
        self.api = client.lowlevel.AioMatrixApi(base_url)
        #self.event_manager = EventManager(self.room_id, self.api)
        self.event_manager = None
        self.url = base_url
        self.username = username
        self.password = password
        self.device_id = device_id
        self.access_token = None
        self.sync_flag = False
        self.listen_room_messages = []
        self.listen_room_typing = []
        self.listen_room_receipt = []
        #self.listen_queue = asyncio.Queue(loop=asyncio.get_event_loop())

        logging.basicConfig(format='[%(levelname)s] %(message)s', level=log_level)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.api:
            await self.api.close()

    async def connect(self):
        """Connects to the server and logs in using the username/password provided."""
        resp = await self.api.connect('m.login.password',
                                      user=self.username,
                                      password=self.password,
                                      device_id=self.device_id)
        self.access_token = resp['access_token']
        self.api.set_access_token(self.access_token)
        logging.info("Successfully connected user \"%s\".", self.username)

    async def room_join(self, room_alias_or_id):
        """Joins a room.
        :param room_alias_or_id: ID or alias of the room to join.
        :return Room: Instance of the Room class.
        """
        response = await self.api.room_join(room_alias_or_id)
        room_id = response['room_id']
        self.event_manager = EventManager(room_id, self.api)
        return Room(self, self.api, self.event_manager, room_id,
                    room_alias_or_id if room_id != room_alias_or_id else None)

    async def room_create(self, room_alias, name, invitees, public=False):
        """
        Ceate a room.
        :param room_alias: Alias of the room.
        :param name: Displayed name of the room.
        :param invitees: List of invitees.
        :param public: True means public, False means private, default private.
        :return: Room: Instance of the Room class
        """
        response = await self.api.room_create(room_alias, name, invitees, public)
        room_id = response['room_id']
        room_alias = response['room_alias']
        return Room(self, self.api, room_id, room_alias)

    async def get_invite(self):
        """
        Yields room invite events whenever they occur.
        :return: RoomID, Room Name, Sender
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_customer("invite", temp_queue)

        while True:
            try:
                room_id, name, sender = await temp_queue.get()
                yield room_id, name, sender
            except asyncio.CancelledError:
                await self.event_manager.remove_customer("invite", temp_queue)


    #region Sync Methods

    '''async def _start_sync(self):
        await self.__set_sync_flag(True)

        loop = asyncio.get_event_loop()
        loop.create_task(self.__sync_task())

        #TODO help, how to compare tasks?
        if self.__sync_task() in asyncio.Task.all_tasks():
            print('yo')
        print(asyncio.Task.all_tasks())'''

    '''async def _stop_sync(self):
        await self.__set_sync_flag(False)

    async def __sync_task(self):
        # Remove old events (set since_token to now)
        resp_json = await self.api.sync()
        self.api.set_since_token(resp_json["next_batch"])

        # Start waiting for new events
        while self.sync_flag:
            filter_timeline, filter_ephemeral = self.__get_current_sync_filters()
            resp_json = await self.api.sync(filter_timeline_types=filter_timeline,
                                            filter_ephemeral_types=filter_ephemeral)
            self.api.set_since_token(resp_json["next_batch"])

            if self.listen_room_messages:
                for entry in self.listen_room_messages:
                    room_id = entry['room_id']
                    callback = entry['callback']
                    if room_id in resp_json['rooms']['join']:
                        for event in resp_json['rooms']['join'][room_id]['timeline']['events']:
                            callback(room_id, event['sender'], event['content']['body'])
                            #self.listen_queue.put_nowait((room_id, event['sender'], event['content']['body']))

            if self.listen_room_typing:
                for entry in self.listen_room_typing:
                    room_id = entry['room_id']
                    callback = entry['callback']
                    if room_id in resp_json['rooms']['join']:
                        for event in resp_json['rooms']['join'][room_id]['ephemeral']['events']:
                            if 'user_ids' in event['content']:
                                callback(room_id, event['content']['user_ids'])

            # TODO content mapping (?)
            if self.listen_room_receipt:
                for entry in self.listen_room_receipt:
                    room_id = entry['room_id']
                    callback = entry['callback']
                    if room_id in resp_json['rooms']['join']:
                        print(resp_json)'''

    '''async def __set_sync_flag(self, start):
        async with asyncio.Lock():
            if start:
                self.sync_flag = True
            else:
                # Check if there is still an entry in one of the listener lists
                if not self.listen_room_messages \
                        and not self.listen_room_receipt \
                        and not self.listen_room_typing:
                    self.sync_flag = False
                    #TODO empty queue?

    def __get_current_sync_filters(self):
        # Timeline
        timeline_filters = 'm.room.message' if self.listen_room_messages else ''
        # Ephemeral
        ephemeral_filters = []
        if self.listen_room_receipt:
            ephemeral_filters.append('m.receipt')
        if self.listen_room_typing:
            ephemeral_filters.append('m.typing')
        return timeline_filters, ephemeral_filters'''


    #endregion
