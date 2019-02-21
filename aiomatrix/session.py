import asyncio
import logging

from aiomatrix.room import Room
from aiomatrix.eventmanager import EventManager
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
        self.access_token = None

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

    #async def testEnc(self):
    #    await self.api.setup_olm()

    # endregion
