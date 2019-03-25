from urllib.parse import quote_plus
import logging
import json
import aiohttp
import olm

from aiomatrix.errors import AiomatrixError


class AioMatrixApi:
    """Low level class. Uses the aiohttp class to send/receive HTTP requests/responses"""
    def __init__(self, base_url, supported_encryption_version):
        self.http_session = aiohttp.ClientSession()
        self.url = base_url
        self.supported_encryption_version = supported_encryption_version
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

    async def room_create(self, name, invitees, room_alias, public=False,):
        """
        Creates a request for room creation.
        :param name: Name of the room.
        :param invitees: List of users to invite when the room is created.
        :param room_alias: Alias name of the room.
        :param public: Visibility of the created room.
        :return: Response in JSON format.
        """
        json_para = {
            "visibility": "public" if public else "private"
        }
        if name:
            json_para["name"] = name
        if invitees:
            json_para["invite"] = invitees
        if room_alias:
            json_para["room_alias_name"] = room_alias

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
            user_names.append((user, members['joined'][user]['display_name']))

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
    async def get_user_device_ids(self, acc_user_id):
        """
        Returns all device IDs that can be found for the given user.
        :param acc_user_id: User ID, e.g. @bla:matrix.org
        :return: List of all found device IDs.
        """
        resp_json = await self.keys_query(acc_user_id)

        return list(resp_json['device_keys'][acc_user_id].keys())

    async def keys_query(self, acc_user_id):
        """
        Querys the device keys for a given user.
        :param acc_user_id: User ID, e.g. @bla:matrix.org
        :return: JSON response string.
        """
        json_para = {
            "timeout": 10000,
            "device_keys": {
                acc_user_id: []
            },
            "token": "string"
        }
        return await self.__send_request('POST', 'keys/query', json_para)

    async def keys_query_and_verify(self, acc_user_id, acc_device_id):
        """
        Querys and verifies the device keys (identity/sign) for a given device and user.
        :param acc_user_id: User ID e.g. @bla:matrix.org
        :param acc_device_id: Device ID e.g. "HAJSDKLSP"
        :return: If successful: returns validated Device Identity curve25519 and Signing ed25519 key.
        """
        # querys all keys and verifies the ones for the given device, returns id/sign key
        resp_json = await self.keys_query(acc_user_id)

        # Verify the correctness of the keys
        if acc_device_id in list(resp_json['device_keys'][acc_user_id].keys()):
            device_id = acc_device_id
        else:
            raise AiomatrixError("Unknown device " + acc_device_id + ". Cannot query required device keys.")

        # Parse keys
        dev_key_id = resp_json['device_keys'][acc_user_id][device_id]['keys']['curve25519:' + device_id]
        dev_key_sign = resp_json['device_keys'][acc_user_id][device_id]['keys']['ed25519:' + device_id]
        signature = resp_json['device_keys'][acc_user_id][device_id]['signatures'][acc_user_id][
            'ed25519:' + device_id]

        logging.debug("Identity keys info for \"%s\": \"%s\" \"%s\" \"%s\"", device_id, dev_key_id, dev_key_sign,
                      signature)

        keys_json = resp_json['device_keys'][acc_user_id][device_id]
        del keys_json['signatures']
        del keys_json['unsigned']

        olm.ed25519_verify(dev_key_sign, AioMatrixApi.canonical_json(keys_json), signature)

        return dev_key_id, dev_key_sign

    async def keys_claim(self, acc_user_id, acc_device_id):
        """
        Claims one one-time-key of a given user.
        :param acc_user_id: User ID, e.g. @bla:matrix.org
        :param acc_device_id: Device ID e.g. "ASDKWLDPS"
        :return: JSON response string containing the OTK.
        """
        # Only claims ONE one-time-key!
        json_para = {
            "timeout": 10000,
            "one_time_keys": {
                acc_user_id: {
                    acc_device_id: "signed_curve25519"
                }
            }
        }
        return await self.__send_request('POST', 'keys/claim', json_para)

    async def keys_claim_and_verify(self, acc_user_id, acc_device_id, acc_sign_key):
        """
        Claims and returns one OTK for a given user and device
        :param acc_user_id: User ID, e.g. @bla:matrix.org
        :param acc_device_id: Device ID e.g. "ASDKDWLDPS"
        :param acc_sign_key: User ed25519 device signing key (used for the verification)
        :return: If valid key retrieved, OTK is returned
        """
        resp_json = await self.keys_claim(acc_user_id, acc_device_id)

        # No one-time-keys exist
        if not resp_json['one_time_keys']:
            logging.warning("No one-time-key exists for: \"%s\" \"%s\"", acc_user_id, acc_device_id)
            return None

        key_description = list(resp_json['one_time_keys'][acc_user_id][acc_device_id].keys())[0]
        otk = resp_json['one_time_keys'][acc_user_id][acc_device_id][key_description]['key']
        otk_signature = \
            resp_json['one_time_keys'][acc_user_id][acc_device_id][key_description]['signatures'][acc_user_id][
                'ed25519:' + acc_device_id]

        logging.debug("OTK key info for \"%s\": \"%s\" \"%s\"", acc_device_id, otk, otk_signature)

        otk_json = {'key': otk}

        olm.ed25519_verify(acc_sign_key, AioMatrixApi.canonical_json(otk_json), otk_signature)

        return otk

    async def encrypt_room(self, room_id):
        """
        Sends a m.room.encryption message to the room.
        :param room_id: Room ID.
        :return: JSON response (should not be required)
        """
        json_para = {
            "algorithm": self.supported_encryption_version,
            "rotation_period_ms": 604800000,
            "rotation_period_msgs": 100
        }
        return await self._room_send_state_event(room_id, 'm.room.encryption', json_para)

    async def send_olm_pr_msg(self, receiver, rec_dev_id, rec_dev_key, rec_sign_key, sen_user_id, sen_dev_id, sen_dev_key, sen_key_sign, ses):
        """
        Creates and sends the Olm PreKey Message.
        :param receiver: Receiver User ID.
        :param rec_dev_id: Receiver Device ID.
        :param rec_dev_key: Receiver Device curve25519 identification key.
        :param rec_sign_key: Receiver Devie ed25519 signing key.
        :param sen_user_id: Sender User ID.
        :param sen_dev_id: Sender Device ID.
        :param sen_dev_key: Sender Device curve 25519 identification key.
        :param sen_key_sign: Sender Device ed25519 signing key.
        :param ses: Olm Session used for encrypting the prekey message.
        :return: JSON response.
        """
        payload_json = {
            "sender": sen_user_id,
            "sender_device": sen_dev_id,
            "keys": {
                "ed25519": sen_key_sign
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

    async def send_megolm_pr_msg(self, room_id, receiver, sen_dev_key, sen_user_id, sen_key_sign, rec_dev_id, rec_key_sign, rec_dev_key, ses, megses):
        """
        Creates and sends a MegOlm prekey message for a given room, sender and receiver.
        :param room_id: Room ID.
        :param receiver: Receiver User ID.
        :param sen_dev_key: Sender Device curve25519 identification key.
        :param sen_user_id: Sender User ID.
        :param sen_key_sign: Sender Signing ed25519 key.
        :param rec_dev_id: Receiver Device ID.
        :param rec_key_sign: Receiver ed25519 signing key.
        :param rec_dev_key: Receiver curve25519 device key.
        :param ses: Olm session used to encrypt the message.
        :param megses: MegOlm session used to encrypt the content and create the session keys.
        :return: JSON response.
        """
        ses_key = megses.session_key

        room_key_event = {
            "content": {
                "algorithm": self.supported_encryption_version,
                "room_id": room_id,
                "session_id": megses.id,
                "session_key": ses_key
            },
            "type": "m.room_key",
            "keys": {
                "ed25519": sen_key_sign
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
                                "type": 0  # Important, is a olm pre key message even though it is encrypted with olm
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
        """
        Sends a m.room.encrypted message to a given room.
        :param room_id: Room ID.
        :param sen_dev_id: Sender Device ID.
        :param sen_dev_key: Sender Device curve25519 identification key.
        :param megses: MegOlm session used to encrypted the message content.
        :param msg: Plaintext message.
        :return: JSON response
        """
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
            "algorithm": self.supported_encryption_version,
            "ciphertext": enc_msg,
            "device_id": sen_dev_id,
            "sender_key": sen_dev_key,
            "session_id": megses.id
        }

        return await self.__send_request('PUT', 'rooms/' + quote_plus(room_id) + "/send/m.room.encrypted/" + str(self.__get_new_txn_id()), json_para)

    async def device_keys_upload(self, acc, user_id, device_id):
        """
        Uploads new device key for the given user (curve25519 and ed25519)
        :param acc: Olm Account.
        :param user_id: User ID.
        :param device_id: User device ID.
        :return: JSON response.
        """
        dev_key_id = acc.identity_keys["curve25519"]
        dev_key_sig = acc.identity_keys["ed25519"]

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
            }
        }

        await self.__send_request('POST', "keys/upload", json_para)

    async def otk_upload(self, acc, user_id, device_id, amount=10):
        """
        Uploads new OTK for a given user/device.
        :param acc: Olm account.
        :param user_id: User ID.
        :param device_id: Device ID.
        :param amount: Amount of keys to be generated and uploaded.
        :return: JSON response
        """
        acc.generate_one_time_keys(amount)
        keys = list(acc.one_time_keys["curve25519"].keys())
        values = list(acc.one_time_keys["curve25519"].values())
        acc.mark_keys_as_published()

        json_para = {'one_time_keys': {}}
        for key, value in zip(keys, values):
            json_para['one_time_keys']["signed_curve25519:" + key] = {
                "key": value,
                "signatures": {
                    user_id: {
                        "ed25519:" + device_id: acc.sign(AioMatrixApi.canonical_json({'key': value}))
                    }
                }
            }

        resp_json = await self.__send_request('POST', "keys/upload", json_para)

        return resp_json['one_time_key_counts']['signed_curve25519']

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
                                                json=json_para)
        elif http_type == 'PUT':
            resp = await self.http_session.put(self.url + '/_matrix/client/r0/' + url_extension,
                                               params=url_params,
                                               json=json_para)
        elif http_type == 'GET':
            resp = await self.http_session.get(self.url + '/_matrix/client/r0/' + url_extension,
                                               params=url_params,
                                               json=json_para)
        elif http_type == 'DELETE':
            resp = await self.http_session.delete(self.url + '/_matrix/client/r0/' + url_extension,
                                                  params=url_params,
                                                  json=json_para)
        else:
            raise AiomatrixError('Access_token - Unknown HTTP method type:' + http_type)

        # Error handling
        logging.debug(" \"%s\" - Response status code: \"%d\"", url_extension, resp.status)
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
        """
        Creates a canonical JSON UTF string out of a JSON. Used to creeate singing content for encryption.
        :param value: JSON
        :return: UTF-8 String.
        """
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
