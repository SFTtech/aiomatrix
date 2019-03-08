import asyncio
import logging
import os
import pickle
import olm

from aiomatrix.room import Room
from aiomatrix.eventmanager import EventManager
from .api import client


class Session:
    """Creates a personalized connection to a matrix server."""
    def __init__(self, username, password, base_url, device_id=None, log_level=20, save_directory_path='./save/'):
        """
        Initializes a new session.
        :param username: Username, e.g. "test"
        :param password: Password for the given user.
        :param base_url: Url for the server e.g. "https://matrix.org"
        :param device_id: Id of the device you're logging onto. Important: For encryption the device
        name has to be specified!
        :param log_level: Level of the logging printouts: (Default)INFO = 20, DEBUG = 10
        :param save_directory_path: Path where all the session/key/account relevant information of the
        encryption is saved to (e.g. ./blaa/)
        """
        self.supported_encryption_version = 'm.megolm.v1.aes-sha2'
        self.api = client.lowlevel.AioMatrixApi(base_url, self.supported_encryption_version)
        self.event_manager = EventManager(self.api)
        self.url = base_url
        self.username = username
        self.password = password
        self.device_id = device_id
        self.save_directory_path = save_directory_path
        self.user_id = None
        self.access_token = None

        self.olm_account = None
        self.device_key = None
        self.sign_key = None
        self.olm_sessions = dict()

        # Load all know olm sessions in case the partner wants to use them for other rooms to send megOlm keys
        # TODO user specific pickle (user id, device id)
        if os.path.exists(self.save_directory_path + 'olmSessions.pkl'):
            tmp_dict = self.load_obj('olmSessions')

            for entry in tmp_dict:
                self.olm_sessions[entry] = olm.Session.from_pickle(tmp_dict[entry], self.password)

        logging.basicConfig(format='[%(levelname)s] %(message)s', level=log_level)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.api:
            await self.api.close()
        if self.olm_account:
            pick_path = self.save_directory_path + self.username + self.device_id
            pickled = self.olm_account.pickle(self.password)
            file_handle = open(pick_path, 'wb+')
            file_handle.write(pickled)
            file_handle.close()

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
            logging.warning("No explicit device ID given during session setup, will use "
                            "the server generated new device ID: \"%s\"", self.device_id)
            self.device_id = resp['device_id']
        self.access_token = resp['access_token']
        self.api.set_access_token(self.access_token)

        # load olm account for this user
        self.olm_account = await self.__create_or_load_olm_account(self.password)

        logging.info("Successfully connected user \"%s\".", self.username)

    def get_user_id(self):
        """
        Returns the user ID.
        :return: User ID, e.g. @example:matrix.org
        """
        return self.user_id

    def get_device_id(self):
        """
        Returns the device ID or Device Name.
        :return: Device ID e.g. HWHWKDO9
        """
        return self.device_id

    def get_olm_account(self):
        """
        Returns the olm account instance for this device/session.
        :return: Olm account instance.
        """
        return self.olm_account

    def get_device_key(self):
        """
        Returns the curve25519 device identification key of this device.
        :return: Curve25519 device ID key.
        """
        return self.device_key

    def get_sign_key(self):
        """
        Returns the ed25519 device signing key, sometimes referred as footprint.
        :return: Ed25519 device signing key.
        """
        return self.sign_key

    def get_supported_encryption_version(self):
        """
        Returns the, by this device, supported MegOlm encryption version.
        :return: Supported MegOlm encryption version e.g. 'm.megolm.v1.aes-sha2'
        """
        return self.supported_encryption_version

    def get_save_directory_path(self):
        """
        Returns the path where all the long term information of encryption gets saved into.
        :return: Save directory path.
        """
        return self.save_directory_path

    def get_password(self):
        """
        Returns the user's password, which is also used for pickling keys/session of Olm/MegOlm
        :return: User's password.
        """
        return self.password

    def get_olm_session(self, user_id, key):
        """
        Gets a stored olm session referenced by the user's ID and device key.
        :param user_id: User id, e.g. @bla:matrix.org
        :param key: Device key, ed25519 key of the user.
        :return: Olm Session object.
        """
        return self.olm_sessions[(user_id, key)]

    def set_olm_session(self, user_id, key, ses):
        """
        Adds an olm session to the global olm_session dict.
        :param user_id: User id, e.g. @bla:matrix.org
        :param key: Device key, ed25519 key of the user.
        :param ses: OutBound or InBound Olm session.
        """
        self.olm_sessions[(user_id, key)] = ses

        tmp_dict = dict()

        for entry in self.olm_sessions:
            tmp_dict[entry] = self.olm_sessions[entry].pickle(self.password)

        self.save_obj(tmp_dict, "olmSessions")

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

    async def room_create(self, name, invitees, room_alias=None, public=False):
        """
        Create a room.
        :param name: Displayed name of the room.
        :param invitees: List of invitees.
        :param room_alias: Alias of the room.
        :param public: True means public, False means private, default private.
        :return: Room: Instance of the Room class.
        """
        response = await self.api.room_create(name, invitees, room_alias, public)
        room_id = response['room_id']
        if 'room_alias' in response:
            room_alias = response['room_alias']
        else:
            room_alias = None
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
                await self.event_manager.remove_subscriber("invite", temp_queue)

    # endregion

    # region Encryption

    async def get_otk_count(self):
        """
        Yields room invite events whenever they occur.
        :return: RoomID, Room Name, Sender
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("otk", temp_queue)

        while True:
            try:
                otk_count = await temp_queue.get()
                yield otk_count
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("otk", temp_queue)

    async def __create_or_load_olm_account(self, password):
        """
        Creates or loads an olm account. If an account for this device ID (used at session setup) was already pickled
        it is loaded, otherwise a new account is created and the device key pair, signing key pair and one-time key
        pairs are uploaded to the server. After uploading, this account is pickled and the next time this device
        is used these information are loaded instead of created.
        :param password: User's password, used for securing the pickled account.
        :return: Instance of an olm account.
        """
        # save acc and only load if not saved before to make sure to use the same keys every time
        pick_path = self.save_directory_path + self.username + self.device_id

        # an account with corresponding keys has not been pickled for this user + device combo
        if not os.path.exists(pick_path):
            acc = olm.Account()

            # Upload new keys to the server
            await self.api.device_keys_upload(acc, self.user_id, self.device_id)
            # Upload OTKs
            # "The maximum number of active keys supported by libolm is returned by olm_account_max_number_
            # of_one_time_keys. The client should try to maintain about half this number on the homeserver."
            # From https://matrix.org/docs/guides/e2e_implementation.html
            await self.api.otk_upload(acc, self.user_id, self.device_id, acc.max_one_time_keys/2)

            pickled = acc.pickle(password)
            file_handle = open(pick_path, 'wb+')
            file_handle.write(pickled)
            file_handle.close()
        else:
            with open(pick_path, 'rb') as file_handle:
                pick = file_handle.read()
                acc = olm.Account.from_pickle(pick, password)

        # Set local device public key, used and required for encrypting messages
        self.device_key = acc.identity_keys["curve25519"]
        self.sign_key = acc.identity_keys["ed25519"]

        logging.debug("Device identity/sign key info for \"%s\": \"%s\" \"%s\"", self.device_id,
                      acc.identity_keys["curve25519"], acc.identity_keys["ed25519"])

        self.olm_account = acc

        return acc

    # endregion

    def save_obj(self, obj, name):
        """
        General method to pickle an object.
        :param obj: Any kind of object, here mainly dicts.
        :param name: File name, ".pkl" will get added.
        """
        with open(self.save_directory_path + name + '.pkl', 'wb') as file_handle:
            pickle.dump(obj, file_handle, pickle.HIGHEST_PROTOCOL)

    def load_obj(self, name):
        """
        General method to load a pickled object.
        :param name: File name, ".pkl" will be added.
        :return: Un-pickled object.
        """
        with open(self.save_directory_path + name + '.pkl', 'rb') as file_handle:
            return pickle.load(file_handle)
