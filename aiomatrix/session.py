import asyncio
import logging
import olm
import os

from aiomatrix.room import Room
from aiomatrix.eventmanager import EventManager
from aiomatrix.errors import AiomatrixError
from .api import client


class Session:
    """Creates a personalized connection to a matrix server."""
    def __init__(self, username, password, base_url, device_id=None, log_level=20):
        """
        Initializes a new session.
        :param username: Username, e.g. "test"
        :param password: Password for the given user.
        :param base_url: Url for the server e.g. "https://matrix.org"
        :param device_id: Id of the device you're logging onto. Important: For encryption the device name has to be specified!
        :param log_level: Level of the logging printouts: (Default)INFO = 20, DEBUG = 10
        """
        self.api = client.lowlevel.AioMatrixApi(base_url)
        self.event_manager = EventManager(self.api)
        self.url = base_url
        self.username = username
        self.password = password
        self.device_id = device_id
        self.user_id = None
        self.access_token = None

        self.olm_account = None
        self.device_key = None
        self.sign_key = None

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
        self.user_id = resp['user_id']
        # If no explicit device ID is used during session setup/connection the randomly generated device ID of the
        # server is set for further usage (e.g. encryption)
        if not self.device_id:
            logging.warning("No explicit device ID given during session setup, will use the server generated new device ID: \"%s\"", self.device_id)
            self.device_id = resp['device_id']
        self.access_token = resp['access_token']
        self.api.set_access_token(self.access_token)

        # load olm account for this user
        self.olm_account = await self.__create_or_load_olm_account(self.password)

        logging.info("Successfully connected user \"%s\".", self.username)

    def get_user_id(self):
        return self.user_id

    def get_device_id(self):
        return self.device_id

    def get_olm_account(self):
        return self.olm_account

    def get_device_key(self):
        return self.device_key

    def get_sign_key(self):
        return self.sign_key

    # region Room Methods

    async def room_join(self, room_alias_or_id):
        """Joins a room. Also serves as an accept of an invite.
        :param room_alias_or_id: ID or alias of the room to join.
        :return Room: Instance of the Room class.
        """
        response = await self.api.room_join(room_alias_or_id)
        room_id = response['room_id']
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
        return Room(self, self.api, self.event_manager, room_id, room_alias)

    async def get_invite(self):
        """
        Yields room invite events whenever they occur.
        :return: RoomID, Room Name, Sender
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("invite", temp_queue)

        while True:
            try:
                room_id, name, sender = await temp_queue.get()
                yield room_id, name, sender
            except asyncio.CancelledError:
                await self.event_manager.add_subscriber("invite", temp_queue)

    # endregion

    # region Encryption

    async def __create_or_load_olm_account(self, password):

        # save acc and only load if not saved before to make sure to use the same keys every time
        pick_path = '/home/andi/devel/matrix/tmp/' + self.username + self.device_id

        # an account with corresponding keys has not been pickled for this user + device combo
        if not os.path.exists(pick_path):
            acc = olm.Account()
            p = acc.pickle(password)
            f = open(pick_path, 'wb+')
            f.write(p)
            f.close()

            # Upload new keys to the server
            await self.api.device_keys_upload(acc, self.user_id, self.device_id)
        else:
            with open(pick_path, 'rb') as f:
                pick = f.read()
                acc = olm.Account.from_pickle(pick, password)

        # We also need control over all one-time-keys, they are somehow not pickled
        # Therefore: Read all existing one-time-keys and upload new ones
        # Not verifying, because if we upload new device keys we don't have the old one to verify it
        # and we simply don't care if they were correct, we only throw them away

        while True:
            resp_json = await self.api.keys_claim(self.user_id, self.device_id)
            if not resp_json['one_time_keys']:
                break

        await self.api.otk_upload(acc, self.user_id, self.device_id)

        # Set local device public key, used and required for encrypting messages
        self.device_key = acc.identity_keys["curve25519"]
        self.sign_key = acc.identity_keys["ed25519"]

        logging.debug("Device identity/sign key info for \"%s\": \"%s\" \"%s\"", self.device_id, acc.identity_keys["curve25519"], acc.identity_keys["ed25519"])

        return acc

    # endregion
