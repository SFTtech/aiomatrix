import asyncio
import logging

from aiomatrix.lowlevel import AioMatrixApi
from aiomatrix.room import Room

class Session():
    def __init__(self, username, password, base_url, device_id=None, log_level=20):
        self.api = AioMatrixApi(base_url)
        self.url = base_url
        self.username = username
        self.password = password
        self.device_id = device_id
        self.access_token = None
        self.sync_flag = False
        self.listen_room_messages = []

        logging.basicConfig(format='[%(levelname)s] %(message)s', level=log_level)

    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.api:
            await self.api.close()

    async def connect(self):
        resp = await self.api.connect('m.login.password',
                                      user=self.username,
                                      password=self.password,
                                      device_id=self.device_id)
        self.access_token = resp['access_token']
        self.api.set_access_token(self.access_token)
        logging.info("Successfully connected user \"%s\".", self.username)

    async def room_join(self, room_alias_or_id):
        response = await self.api.room_join(room_alias_or_id)
        room_id = response['room_id']
        room = Room(self, self.api, room_id,
                    room_alias_or_id if room_id != room_alias_or_id else None)
        return room

    #region Sync Methods

    async def _start_sync(self):
        self.__set_sync_flag(True)

        loop = asyncio.get_event_loop()
        loop.create_task(self.__sync_thread())

    async def _stop_sync(self):
        self.__set_sync_flag(False)

    async def __sync_thread(self):
        # Remove old events (set since_token to now)
        resp_json = await self.api.sync()
        self.api.set_since_token(resp_json["next_batch"])

        # Start waiting for new events
        while self.sync_flag:
            resp_json = await self.api.sync()
            #print(resp_json)
            self.api.set_since_token(resp_json["next_batch"])

            if self.listen_room_messages:
                for entry in self.listen_room_messages:
                    room_id = entry['room_id']
                    callback = entry['callback']
                    if room_id in resp_json['rooms']['join']:
                        for event in resp_json['rooms']['join'][room_id]['timeline']['events']:
                            callback(room_id, event['sender'], event['content']['body'])

    def __set_sync_flag(self, start):
        # TODO: Threadsafe lists and flag?
        if start:
            self.sync_flag = True
        else:
            # Check if there is still an entry in one of the listener lists
            if not self.listen_room_messages:
                self.sync_flag = False

    #endregion
