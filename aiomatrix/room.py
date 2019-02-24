import asyncio
import olm
import logging


class Room:
    """Instance of a matrix room"""
    def __init__(self, session, api, event_manager, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias
        self.event_manager = event_manager
        self.user_id = self.session.get_user_id()
        self.device_id = self.session.get_device_id()

        # Encryption parameters
        self.is_encrypted = False
        self.device_key = self.session.get_device_key()
        self.olm_account = self.session.get_olm_account()
        self.meg_ses = None  #TODO pickle megolm session
        self.room_keys = list()  # Tuples of (user_id, device_id, megolm session key)

    async def invite_user(self, user_id):
        """
        Invites a user to join this room.
        :param user_id: User id e.g. @example:matrix.org
        """
        await self.api.room_invite(self.room_id, user_id)

    async def leave(self):
        """
        Leave the room. It is no longer possible to get message, typing, etc. events of this room.
        """
        await self.api.room_leave(self.room_id)

    async def send_message(self, message):
        """
        Sends a message to the room.
        :param message: Message string
        """
        #TODO update function description
        if self.is_encrypted:
            await self.api.send_enc(self.room_id, self.device_id, self.device_key, self.meg_ses, message)
        else:
            await self.api.room_send_message(self.room_id, message)

    async def set_name(self, name):
        """
        Sets the displayed room name.
        :param name: New name of the room.
        """
        await self.api.room_set_name(self.room_id, name)

    async def set_topic(self, topic):
        """
        Sets the topic, extra information, short description of the room.
        :param topic: Room topic.
        """
        await self.api.room_set_topic(self.room_id, topic)

    async def get_members(self):
        """
        Returns a list of room members as user IDs (@example:matrix.org)
        :return: List of tuples of user IDs and display_names (@example:matrix.org, Bob)
        """
        return await self.api.room_get_members(self.room_id)

    async def get_message(self):
        """
        Yields room message events whenever they occur.
        :return: RoomID, Sender, Message
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("message", temp_queue, self.room_id)
        while True:
            try:
                room_id, sender, message = await temp_queue.get()
                yield room_id, sender, message
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("message", temp_queue, room_id)

    async def get_typing(self):
        """
        Yields room typing events whenever they occur.
        :return: RoomID, Sender
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("typing", temp_queue, self.room_id)

        while True:
            try:
                room_id, sender = await temp_queue.get()
                yield room_id, sender
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("typing", temp_queue, room_id)

    # region Encryption

    async def activate_encryption(self):
        #TODO uncomment later
        # Send event to activate encryption of this room
        #await self.api.encrypt_room(self.room_id)

        # Generate MegOlm keys for this device and for this room
        self.meg_ses = olm.OutboundGroupSession()

        # Loop over all members in this room:
        # - get their keys
        # - create olm session
        # - use olm to pass this room's megolm session info (stored in self.meg_ses)
        room_members = await self.get_members()
        for user_id, _ in room_members:
            # Exclude own user
            if user_id != self.session.get_user_id():
                #TODO How to get user's device ID he joined the room with?
                device_id = 'YPWKTLRKZG'
                self.room_keys.append((user_id, device_id, None))
                await self.__create_room_encryption(user_id, device_id)

    async def __create_room_encryption(self, partner_user_id, partner_device_id):
        self_user_id = self.session.get_user_id()
        self_device_id = self.session.get_device_id()

        # Generate and upload new One Time Keys

        # You can only upload new keys when the old are read (?!)
        # TODO: wtf? why..
        _, sign = await self.api.keys_query(self_user_id, self_device_id)
        await self.api.keys_claim(self_user_id, self_device_id, sign)

        self_otk = await self.api.otk_upload(self.olm_account, self_user_id, self_device_id)

        # Get partner Identity Keys

        partner_dev_key_id, partner_dev_key_sign = await self.api.keys_query(partner_user_id, partner_device_id)

        # Get partner One-Time Key

        partner_otk = await self.api.keys_claim(partner_user_id, partner_device_id, partner_dev_key_sign)

        # Olm Session
        ses = olm.OutboundSession(self.olm_account, partner_dev_key_id, partner_otk)

        await self.api.send_olm_pr_msg(partner_user_id, partner_device_id, partner_dev_key_id, partner_dev_key_sign,
                                       self_user_id, self_device_id, self.device_key, self_otk, ses)

        # MegOlm Session
        await self.api.send_megolm_pr_msg(self.room_id, partner_user_id, self.device_key, self_user_id, self_otk,
                                          partner_device_id, partner_dev_key_sign, partner_dev_key_id, ses, self.meg_ses)

        # Set this room to encrypted, forces messages to be sent encrypted
        self.is_encrypted = True

    # endregion
