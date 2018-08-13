import aiohttp

from urllib.parse import quote_plus

class AioMatrixApi():
    def __init__(self, base_url):
        self.httpSession = aiohttp.ClientSession()
        self.url = base_url
        self.txn_id = 0
        self.access_token = None

    async def connect(self, login_type, **kwargs):

        json = {"type": login_type}
        for key in kwargs:
            if kwargs[key]:
                json[key] = kwargs[key]

        return await self.__send_request('POST','login', json)

        #TODO special case in connect or in send?
        # Special handling due to unknown access_token
        '''async with self.httpSession.post(self.url + '/_matrix/client/r0/login', json=json) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                err = await resp.json()
                raise Exception(err['errcode'] + ': ' + err['error'])'''

    async def disconnect(self):
        await self.httpSession.close()

    async def room_join(self, room_alias_or_id):
        return await self.__send_request('POST', 'join/' + quote_plus(room_alias_or_id))


    # region Room Specific functions

    async def room_send_message(self, room_id, message):
        json = {'msgtype': 'm.text', 'body': message}
        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) + '/send/m.room.message/' + str(self.__get_new_txn_id()), json)

    # endregion

    # region Private functions

    async def __send_request(self, type, url_extension, json = None):

        if self.access_token == None:
            if type == 'POST':
                resp = await self.httpSession.post(self.url + '/_matrix/client/r0/' + url_extension,
                                                   json=json
                                                   )
            else:
                raise Exception('No access_token - Unknown HTTP method type:' + type)
        else:
            if type == 'POST':
                resp = await self.httpSession.post(self.url + '/_matrix/client/r0/' + url_extension,
                                                   params={'access_token': self.access_token},
                                                   json=json
                                                   )
            elif type == 'PUT':
                resp = await self.httpSession.put(self.url + '/_matrix/client/r0/' + url_extension,
                                                  params={'access_token': self.access_token},
                                                  json=json
                                                  )
            else:
                raise Exception('Access_token - Unknown HTTP method type:' + type)

        # Error handling
        if resp.status != 200:
            err = await resp.json()
            raise Exception(err['errcode'] + ': ' + err['error'])

        return await resp.json()

    def __get_new_txn_id(self):
        self.txn_id += 1
        return self.txn_id

    # endregion



