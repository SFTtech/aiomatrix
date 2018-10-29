from urllib.parse import quote_plus
import logging
import aiohttp

from aiomatrix.errors import AiomatrixError


class AioMatrixApi:
    """Low level class. Uses the aiohttp class to send/receive HTTP requests/responses"""
    def __init__(self, base_url):
        self.http_session = aiohttp.ClientSession()
        self.url = base_url
        self.txn_id = 0
        self.access_token = None
        self.since_token = None

    def set_access_token(self, token):
        """
        Sets the access_token field required to send client-related HTTP requests.
        :param token: access_token, either manually or retrievable
        from the response of the login method.
        """
        self.access_token = token

    def set_since_token(self, token):
        """
        Sets the since_token field relevant for the sync request.
        :param token: since_token field, can be retrieved from sync responses.
        :return:
        """
        self.since_token = token

    def get_since_token(self):
        """
        Returns the since_token field that is actually used in sync requests..
        :return: since_token field.
        """
        return self.since_token

    async def connect(self, login_type, **kwargs):
        """
        Connects to the server by sending a login command with additional parameters.
        :param login_type: Login type (multiple can be supported by the server)
        e.g. "m.login.password"
        :param kwargs: Login parameters, e.g. user, password, device_id as key:value pair
        :return:
        """
        json = {"type": login_type}
        for key in kwargs:
            if kwargs[key]:
                json[key] = kwargs[key]

        return await self.__send_request('POST', 'login', json)

    async def close(self):
        """Closes the aiohttp connection."""
        await self.http_session.close()

    async def room_join(self, room_alias_or_id):
        """
        Sends out a request to join a given room.
        :param room_alias_or_id: Room alias or room ID.
        :return: Response in JSON format.
        """
        return await self.__send_request('POST', 'join/' + quote_plus(room_alias_or_id))

    async def room_create(self, room_alias, name, invitees, public=False,):
        """
        Creates a request for room creation.
        :param room_alias: Alias name of the room.
        :param name: Name of the room.
        :param invitees: List of users to invite when the room is created.
        :param public: Visibility of the created room.
        :return: Response in JSON format.
        """
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
        """
        Sends a sync request and waits for the response depending on the timeout.
        :param event_filter: Filter string, defining which events are relevant.
        :param timeout: Timeout of the request.
        :return: Response in JSON format.
        """
        if self.since_token:
            params = {'since':self.since_token,
                      'full_state':'false'}
        else:
            params = {'full_state':'false'}

        params['timeout'] = str(timeout)

        if event_filter:
            params['filter'] = event_filter

        return await self.__send_request('GET', 'sync', json=None, params=params)

    # region Room Specific functions

    async def room_invite(self, room_id, member):
        return await self.__send_request('POST', 'rooms/' + quote_plus(room_id) + '/invite',
                                         json={'user_id': member})

    async def room_leave(self, room_id):
        """
        Create parameters and URL to leave a given room.
        :param room_id: ID of the room.
        :return: Response in JSON format.
        """
        return await self.__send_request('POST', 'rooms/' + quote_plus(room_id) + '/leave')

    async def room_get_members(self, room_id):
        """
        Create parameters and URL to retrieve all currently joined members of a given room.
        :param room_id: ID of the room.
        :return: List of user IDs (@example:matrix.org)
        """
        members = await self.__send_request('GET', 'rooms/' + quote_plus(room_id) + '/joined_members')

        user_names = []
        for user in members['joined']:
            user_names.append(user)

        return user_names

    async def room_send_message(self, room_id, message):
        """
        Create parameters and URL to send the given message to the reference room.
        :param room_id: ID of the room.
        :param message: Message sent.
        :return: Response in JSON format.
        """
        json = {'msgtype': 'm.text', 'body': message}
        return await self._room_send_event(room_id, 'm.room.message', json)

    async def room_set_topic(self, room_id, topic):
        """
        Create parameters and URL to set the topic of the referenced room.
        :param room_id: ID of the room.
        :param topic: Room topic.
        :return: Response in JSON format.
        """
        json = {'topic': topic}
        return await self._room_send_state_event(room_id, 'm.room.topic', json)

    async def room_set_name(self, room_id, name):
        """
        Create parameters and URL to set the name of the referenced room.
        :param room_id: ID of the room.
        :param name: Room name.
        :return: Response in JSON format.
        """
        json = {'name': name}

        return await self._room_send_state_event(room_id, 'm.room.name', json)

    async def _room_send_event(self, room_id, event, json):
        """
        Create parameters and URL to send the event to the referenced room.
        :param room_id: ID of the room.
        :param event: Event identifying sting.
        :param json: JSON event parameters.
        :return: Response in JSON format.
        """
        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) +
                                         '/send/' + quote_plus(event) + '/'
                                         + str(self.__get_new_txn_id()), json)

    async def _room_send_state_event(self, room_id, event, json):
        """
        Create parameters and URL to send the state event to the referenced room.
        :param room_id: ID of the room.
        :param event: Event identifying sting.
        :param json: JSON event parameters.
        :return: Response in JSON format.s
        """
        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) +
                                         '/state/' + quote_plus(event), json)

    # endregion

    # region Private functions

    async def __send_request(self, http_type, url_extension, json=None, params=None):
        """
        Sends an HTTP request depending on the parameters. Handles response status code and might
        throw an AiomatrixError.
        :param http_type: 'POST', 'PUT' or 'GET'
        :param url_extension: URL command extension added to the standard matrix client url.
        :param json: JSON parameters for this request.
        :param params: URL parameters for the request.
        :return: Response in JSON format.
        """

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
        """
        Creates a unique transaction ID.
        At the moment not checked for overflow. Specification unclear.
        :return: Transaction ID.
        """
        self.txn_id += 1
        return self.txn_id

    # endregion
