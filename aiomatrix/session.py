#TODO logging
#TODO own error class

from aiomatrix.lowlevel import AioMatrixApi
from aiomatrix.room import Room

class Session():
    def __init__(self, username_or_id, password, base_url = None, device_id = None):

        if base_url == None and ':' in username_or_id:
            split = username_or_id.split(':')
            if len(split) != 2:
                raise Exception('Base_url or valid user_id required.')
            username = split[0][1:]
            base_url = 'https://' + split[1]

        self.api = AioMatrixApi(base_url)
        self.url = base_url
        self.username = username
        self.password = password
        self.device_id = device_id

    async def connect(self):
        resp = await self.api.connect('m.login.password', user=self.username, password=self.password, device_id=self.device_id)
        self.access_token = resp['access_token']
        self.api.access_token = self.access_token


    async def disconnect(self):
        await self.api.disconnect()

    async def room_join(self, room_alias_or_id):
        response = await self.api.room_join(room_alias_or_id)
        room_id = response['room_id']
        room = Room(self.api, room_id, room_alias_or_id if room_id != room_alias_or_id else None)
        return room


