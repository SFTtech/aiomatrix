from urllib.parse import quote_plus
import logging
import aiohttp

from aiomatrix.errors import AiomatrixError


class AioMatrixApi:
    def __init__(self, base_url):
        self.http_session = aiohttp.ClientSession()
        self.url = base_url
        self.txn_id = 0
        self.access_token = None
        self.since_token = None

    def set_access_token(self, token):
        self.access_token = token

    def set_since_token(self, token):
        self.since_token = token

    async def connect(self, login_type, **kwargs):
        json = {"type": login_type}
        for key in kwargs:
            if kwargs[key]:
                json[key] = kwargs[key]

        return await self.__send_request('POST', 'login', json)

    async def close(self):
        await self.http_session.close()

    async def room_join(self, room_alias_or_id):
        return await self.__send_request('POST', 'join/' + quote_plus(room_alias_or_id))

    async def room_create(self, room_alias, name, invitees, public=False,):

        json = {
            "visibility": "public" if public else "private"
        }
        if room_alias:
            json["room_alias_name"] = room_alias
        if name:
            json["name"] = name
        if invitees:
            json["invite"] = invitees

        return await self.__send_request('POST', 'createRoom', json)

    async def sync(self, event_filter=None, timeout=30000):
        event_filter = None # used for testing
        if self.since_token:
            params = {'since':self.since_token,
                      'full_state':'false'}
        else:
            params = {'full_state':'false'}

        params['timeout'] = str(timeout)
        #TODO only room filter atm, improve for all possible events
        if event_filter:
            params['filter'] = event_filter

        return await self.__send_request('GET', 'sync', json=None, params=params)

    # region Room Specific functions

    async def room_send_message(self, room_id, message):
        json = {'msgtype': 'm.text', 'body': message}
        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) +
                                         '/send/m.room.message/'
                                         + str(self.__get_new_txn_id()), json)

    # endregion

    # region Private functions

    async def __send_request(self, http_type, url_extension, json=None, params=None):

        url_params = {"access_token": self.access_token} if self.access_token else None
        if params is not None:
            for key in params:
                if params[key]:
                    url_params[key] = params[key]

        if http_type == 'POST':
            resp = await self.http_session.post(self.url + '/_matrix/client/r0/' + url_extension,
                                                params=url_params,
                                                json=json
                                                )
        elif http_type == 'PUT':
            resp = await self.http_session.put(self.url + '/_matrix/client/r0/' + url_extension,
                                               params=url_params,
                                               json=json
                                               )
        elif http_type == 'GET':
            resp = await self.http_session.get(self.url + '/_matrix/client/r0/' + url_extension,
                                               params=url_params,
                                               json=json
                                               )
        else:
            raise AiomatrixError('Access_token - Unknown HTTP method type:' + http_type)

        # Error handling
        logging.debug("Response status code: \"%d\"", resp.status)
        if resp.status != 200:
            err = await resp.json()
            raise AiomatrixError(err['errcode'] + ': ' + err['error'])

        return await resp.json()

    def __get_new_txn_id(self):
        self.txn_id += 1
        return self.txn_id

    # endregion
