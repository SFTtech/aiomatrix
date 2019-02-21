from urllib.parse import quote_plus
import logging
import aiohttp
import olm
import json
import asyncio

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
        json_para = {"type": login_type}
        for key in kwargs:
            if kwargs[key]:
                json_para[key] = kwargs[key]

        return await self.__send_request('POST', 'login', json_para)

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
        json_para = {
            "visibility": "public" if public else "private"
        }
        if room_alias:
            json_para["room_alias_name"] = room_alias
        if name:
            json_para["name"] = name
        if invitees:
            json_para["invite"] = invitees

        return await self.__send_request('POST', 'createRoom', json_para)

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

        return await self.__send_request('GET', 'sync', json_para=None, params=params)

    async def delete_device(self, device_id):
        '''json_para = {
            "auth": {
                "type": "m.login.password",
                "access_token": self.access_token
            }
        }'''
        json_para = {
          "flows": [
            {
              "stages": [
                "m.login.password"
              ]
            }
          ],
          "params": {},
          "session": "VsfOaWbquLvScXsqBYDNQTgV"
        }

        return await self.__send_request('DELETE', 'devices/' + device_id, json_para)

    # region Room Specific functions

    async def room_invite(self, room_id, member):
        """
        Create parameters and URL to invite a user to a given room.
        :param room_id: ID of the room.
        :param member: User ID e.g. @example:matrix.org
        :return: Response in JSON format.
        """
        return await self.__send_request('POST', 'rooms/' + quote_plus(room_id) + '/invite',
                                         json_para={'user_id': member})

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
        :return: List of tuples of user IDs and display_names (@example:matrix.org, Bob)
        """
        members = await self.__send_request('GET', 'rooms/' + quote_plus(room_id) +
                                            '/joined_members')

        user_names = []
        for user in members['joined']:
            user_names.append((user,members['joined'][user]['display_name']))

        return user_names

    async def room_send_message(self, room_id, message):
        """
        Create parameters and URL to send the given message to the reference room.
        :param room_id: ID of the room.
        :param message: Message sent.
        :return: Response in JSON format.
        """
        json_para = {'msgtype': 'm.text', 'body': message}
        return await self._room_send_event(room_id, 'm.room.message', json_para)

    async def room_set_topic(self, room_id, topic):
        """
        Create parameters and URL to set the topic of the referenced room.
        :param room_id: ID of the room.
        :param topic: Room topic.
        :return: Response in JSON format.
        """
        json_para = {'topic': topic}
        return await self._room_send_state_event(room_id, 'm.room.topic', json_para)

    async def room_set_name(self, room_id, name):
        """
        Create parameters and URL to set the name of the referenced room.
        :param room_id: ID of the room.
        :param name: Room name.
        :return: Response in JSON format.
        """
        json_para = {'name': name}

        return await self._room_send_state_event(room_id, 'm.room.name', json_para)

    async def _room_send_event(self, room_id, event, json_para):
        """
        Create parameters and URL to send the event to the referenced room.
        :param room_id: ID of the room.
        :param event: Event identifying sting.
        :param json_para: JSON event parameters.
        :return: Response in JSON format.
        """
        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) +
                                         '/send/' + quote_plus(event) + '/'
                                         + str(self.__get_new_txn_id()), json_para)

    async def _room_send_state_event(self, room_id, event, json_para):
        """
        Create parameters and URL to send the state event to the referenced room.
        :param room_id: ID of the room.
        :param event: Event identifying sting.
        :param json_para: JSON event parameters.
        :return: Response in JSON format.s
        """
        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) +
                                         '/state/' + quote_plus(event), json_para)

    # endregion

    # region Encryption

    async def keys_query(self, account):
        json_para = {
            "timeout": 10000,
            "device_keys": {
                account: []
            },
            "token": "string"
        }
        return await self.__send_request('POST', 'keys/query', json_para)

    async def keys_claim(self, account, device_id):
        json_para = {
          "timeout": 10000,
          "one_time_keys": {
            account: {
              device_id: "signed_curve25519"
            }
          }
        }
        return await self.__send_request('POST', 'keys/claim', json_para)

    async def encrypt_room(self, room_id):
        json_para = {
                "algorithm": "m.megolm.v1.aes-sha2",
                "rotation_period_ms": 604800000,
                "rotation_period_msgs": 100
        }
        return await self._room_send_state_event(room_id, 'm.room.encryption', json_para)

    async def send_olm_pr_msg(self, receiver, rec_dev_id, rec_dev_key, rec_sign_key, sen_user_id, sen_dev_id, sen_dev_key, sen_otk, ses):
        payload_json = {
            "sender": sen_user_id,
            "sender_device": sen_dev_id,
            "keys": {
                "ed25519": sen_otk
            },
            "recipient": receiver,
            "recipient_keys": {
                "ed25519": rec_sign_key
            }
        }

        initial_message = ses.encrypt(json.dumps(payload_json))

        json_para = {
            "messages": {
                receiver: {
                    rec_dev_id: {
                        "algorithm": "m.olm.v1.curve25519-aes-sha2",
                        "ciphertext": {
                            rec_dev_key: {
                                "body": initial_message.ciphertext,
                                "type": 0
                            }
                        },
                        "sender_key": sen_dev_key
                    },
                    "type": "m.room.encrypted"
                }
            }
        }
        return await self.__send_request('PUT', "sendToDevice/m.room.encrypted/"+str(self.__get_new_txn_id()), json_para)

    async def send_megolm_pr_msg(self, room_id, receiver, sen_dev_key, sen_user_id, sen_otk, rec_dev_id, rec_key_sign, rec_dev_key, ses, megses):
        ses_key = megses.session_key

        room_key_event = {
            "content": {
                "algorithm": "m.megolm.v1.aes-sha2",
                "room_id": room_id,
                "session_id": megses.id,
                "session_key": ses_key
            },
            "type": "m.room_key",
            "keys": {
                "ed25519": sen_otk
            },
            "recipient": receiver,
            "sender": sen_user_id,
            "recipient_keys": {
                "ed25519": rec_key_sign
            }
        }
        room_key_enc = ses.encrypt(json.dumps(room_key_event))

        json_para = {
            "messages": {
                receiver: {
                    rec_dev_id: {
                        "algorithm": "m.olm.v1.curve25519-aes-sha2",
                        "ciphertext": {
                            rec_dev_key: {
                                "body": room_key_enc.ciphertext,
                                "type": 0
                            }
                        },
                        "sender_key": sen_dev_key,
                        "session_id": ses.id
                    },
                    "type": "m.room.encrypted"
                }
            }
        }

        return await self.__send_request('PUT', "sendToDevice/m.room.encrypted/" + str(self.__get_new_txn_id()), json_para)

    async def send_enc(self, room_id, sen_dev_id, sen_dev_key, megses, msg):

        # Create content
        json_content = {
            "room_id": room_id,
            "type": "m.room.message",
            "content": {
                "msgtype": "m.text",
                "body": msg
            }
        }

        enc_msg = megses.encrypt(json.dumps(json_content))

        json_para = {
                    "algorithm": "m.megolm.v1.aes-sha2",
                    "ciphertext": enc_msg,
                    "device_id": sen_dev_id,
                    "sender_key": sen_dev_key,
                    "session_id": megses.id
            }

        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) + "/send/m.room.encrypted/" + str(self.__get_new_txn_id()), json_para)

    async def keys_upload(self, acc, user_id, device_id):

        dev_key_id = acc.identity_keys["curve25519"]
        dev_key_sig = acc.identity_keys["ed25519"]

        acc.generate_one_time_keys(1)
        one_time_key_key = list(acc.one_time_keys["curve25519"].keys())[0]
        one_time_key_value = list(acc.one_time_keys["curve25519"].values())[0]
        acc.mark_keys_as_published()

        sign_info = {
            "user_id": user_id,
            "device_id": device_id,
            "algorithms": [
                "m.olm.v1.curve25519-aes-sha2",
                "m.megolm.v1.aes-sha2"
            ],
            "keys": {
                "curve25519:" + device_id: dev_key_id,
                "ed25519:" + device_id: dev_key_sig
            }
        }

        json_para = {
            "device_keys": {
                "user_id": user_id,
                "device_id": device_id,
                "algorithms": [
                    "m.olm.v1.curve25519-aes-sha2",
                    "m.megolm.v1.aes-sha2"
                ],
                "keys": {
                    "curve25519:" + device_id: dev_key_id,
                    "ed25519:" + device_id: dev_key_sig
                },
                "signatures": {
                    user_id: {
                        "ed25519:" + device_id: acc.sign(AioMatrixApi.canonical_json(sign_info))
                    }
                }
            },
            "one_time_keys": {
                "signed_curve25519:" + one_time_key_key: {
                    "key": one_time_key_value,
                    "signatures": {
                        user_id: {
                            "ed25519:" + device_id: acc.sign(AioMatrixApi.canonical_json({"key": one_time_key_value}))
                        }
                    }
                }
            }
        }

        await self.__send_request('POST', "keys/upload", json_para)

    async def otk_upload(self, acc, user_id, device_id):
        acc.generate_one_time_keys(1)
        one_time_key_key = list(acc.one_time_keys["curve25519"].keys())[0]
        one_time_key_value = list(acc.one_time_keys["curve25519"].values())[0]
        acc.mark_keys_as_published()

        json_para = {
            "one_time_keys": {
                "signed_curve25519:" + one_time_key_key: {
                    "key": one_time_key_value,
                    "signatures": {
                        user_id: {
                            "ed25519:" + device_id: acc.sign(AioMatrixApi.canonical_json({"key": one_time_key_value}))
                        }
                    }
                }
            }
        }

        await self.__send_request('POST', "keys/upload", json_para)
        return one_time_key_value

    # endregion

    # region Private functions

    async def __send_request(self, http_type, url_extension, json_para=None, params=None):
        """
        Sends an HTTP request depending on the parameters. Handles response status code and might
        throw an AiomatrixError.
        :param http_type: 'POST', 'PUT' or 'GET'
        :param url_extension: URL command extension added to the standard matrix client url.
        :param json_para: JSON parameters for this request.
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
                                                json=json_para
                                                )
        elif http_type == 'PUT':
            resp = await self.http_session.put(self.url + '/_matrix/client/r0/' + url_extension,
                                               params=url_params,
                                               json=json_para
                                               )
        elif http_type == 'GET':
            resp = await self.http_session.get(self.url + '/_matrix/client/r0/' + url_extension,
                                               params=url_params,
                                               json=json_para
                                               )
        elif http_type == 'DELETE':
            resp = await self.http_session.delete(self.url + '/_matrix/client/r0/' + url_extension,
                                               params=url_params,
                                               json=json_para
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

    @staticmethod
    def canonical_json(value):
        return json.dumps(
            value,
            # Encode code-points outside of ASCII as UTF-8 rather than \u escapes
            ensure_ascii=False,
            # Remove unnecessary white space.
            separators=(',', ':'),
            # Sort the keys of dictionaries.
            sort_keys=True,
            # Encode the resulting unicode as UTF-8 bytes.
        ).encode("UTF-8")

    # endregion
