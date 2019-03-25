import asyncio
import logging
import json
import os
import olm

from aiomatrix.errors import AiomatrixError


class Room:
    """Instance of a matrix room"""
    def __init__(self, session, api, event_manager, room_id, room_alias=None):
        """
        Initializer for a Room class object.
        :param session: Parent session instance.
        :param api: Low level API to send/receive HTTP requests.
        :param event_manager: Event Manager instance for receiving room events.
        :param room_id: Room Identifier.
        :param room_alias: Room alias, this room can also be found using this alias. (Not required)
        """
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
        self.meg_ses = None
        self.room_keys = dict()  # Dict of (user_id, device_id, session_id) : megolm_session_key

        loop = asyncio.get_event_loop()
        loop.create_task(self.wait_room_encryption())
        self.encrypted_task = None
        self.prekey_task = None

        # Load room keys if exist
        if os.path.exists(self.session.get_save_directory_path() + 'megOlmSessions_' + self.room_id + '.pkl'):
            tmp_dict = self.session.load_obj('megOlmSessions_' + self.room_id)

            for entry in tmp_dict:
                # Own inboundGroupSession, session ID for "real" sessions can never be None
                if entry[2] is None:
                    self.meg_ses = olm.OutboundGroupSession.from_pickle(tmp_dict[entry],
                                                                        self.session.get_password())
                    continue
                self.room_keys[entry] = olm.InboundGroupSession.from_pickle(tmp_dict[entry],
                                                                            self.session.get_password())

            # Also this room is encrypted then
            self.is_encrypted = True

            loop = asyncio.get_event_loop()
            self.prekey_task = loop.create_task(self.wait_olm_megolm_prekey())
            self.encrypted_task = loop.create_task(self.wait_enc_message())

    def set_room_key(self, user_id, device_id, meg_ses_id, meg_ses):
        """
        Adds a new entry to the dict of MegOlm room keys.
        :param user_id: User ID, e.g. @bla:matrix.org
        :param device_id: Device ID e.g. "HAJSKOWP0"
        :param meg_ses_id: MegOlm Session ID
        :param meg_ses: MegOlm Outbound-/InboundGroupSession object
        """
        self.room_keys[(user_id, device_id, meg_ses_id)] = meg_ses

        tmp_dict = dict()

        for entry in self.room_keys:
            tmp_dict[entry] = self.room_keys[entry].pickle(self.session.get_password())

        self.session.save_obj(tmp_dict, 'megOlmSessions_' + self.room_id)

    def set_meg_ses(self, meg_ses):
        """
        Sets the local variable meg_ses. Also adds an entry to the room_key dict for pickling
        :param meg_ses: Meg Olm OutboundGroupSession object.
        """
        self.meg_ses = meg_ses
        self.set_room_key(self.user_id, self.device_id, None, meg_ses)

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
        if self.is_encrypted:
            if self.meg_ses is None:
                await self.activate_encryption()
            await self.api.send_enc(self.room_id, self.device_id, self.device_key, self.meg_ses, message)

            # Pickle the OutboundGroupSession (self.meg_ses) because after every sending of a message
            # the ratchet advances. If not pickled after sending, the ratchet will be repeated.
            tmp_dict = dict()

            for entry in self.room_keys:
                tmp_dict[entry] = self.room_keys[entry].pickle(self.session.get_password())

            self.session.save_obj(tmp_dict, 'megOlmSessions_' + self.room_id)
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
                await self.event_manager.remove_subscriber("message", temp_queue, self.room_id)

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
                await self.event_manager.remove_subscriber("typing", temp_queue, self.room_id)

    # region Encryption

    async def activate_encryption(self):
        """
        This method is called to perform the initial message exchange to enable encryption of a room.
        If the room is not yet to be using encryption it will get set. Otherwise the list of room members is
        iterated and for every user/device the MegOlm session keys are exchanged via secure Olm channel.
        :return:
        """
        # Send event to activate encryption of this room if not yet done from either side
        if not self.is_encrypted:
            await self.api.encrypt_room(self.room_id)

        # Generate MegOlm keys for this device and for this room
        self.set_meg_ses(olm.OutboundGroupSession())

        # Start receiving tasks if not done yet
        if self.encrypted_task is None and self.prekey_task is None and self.encrypted_task is None:
            loop = asyncio.get_event_loop()
            self.prekey_task = loop.create_task(self.wait_olm_megolm_prekey())
            self.encrypted_task = loop.create_task(self.wait_enc_message())

        # Save your own session to abele to decrypt events
        self.set_room_key(self.session.get_user_id(), self.session.get_device_id(), self.meg_ses.id,
                          olm.InboundGroupSession(self.meg_ses.session_key))

        # Loop over all members in this room:
        # - get their device ids
        # - get the corresponding keys
        # - create olm session
        # - use olm to pass this room's megolm session info (stored in self.meg_ses)
        room_members = await self.get_members()
        for user_id, _ in room_members:
            # Exclude own user
            if user_id != self.session.get_user_id():
                device_ids = await self.api.get_user_device_ids(user_id)

                # Pass megolm parameters to each device of the room's members
                for device_id in device_ids:
                    await self.__enc_send_megolm_info(user_id, device_id)

    async def __enc_send_megolm_info(self, partner_user_id, partner_device_id):
        """
        Sets up a Olm Session with the corresponding device and passes the MegOlm session keys to initiaize
        encryption.
        :param partner_user_id: The partner's user ID, e.g. @bla:matrix.org
        :param partner_device_id: The partner's device ID, e.g. "HASHDKPS9"
        """
        own_user_id = self.session.get_user_id()
        own_device_id = self.session.get_device_id()
        own_sign_key = self.session.get_sign_key()

        # Get partner Identity Keys
        partner_dev_key_id, partner_dev_key_sign = await self.api.keys_query_and_verify(partner_user_id,
                                                                                        partner_device_id)

        # Get partner One-Time Key
        partner_otk = await self.api.keys_claim_and_verify(partner_user_id, partner_device_id, partner_dev_key_sign)
        if not partner_otk:
            raise AiomatrixError('Room encryption aborted. No OTKs available for:  {0},  {1}'.format(partner_user_id,
                                                                                                     partner_device_id))

        # Olm Session
        ses = olm.OutboundSession(self.olm_account, partner_dev_key_id, partner_otk)

        # Store olm session, might be used by the partner to send his megOlm session keys
        self.session.set_olm_session(partner_user_id, partner_dev_key_id, ses)

        await self.api.send_olm_pr_msg(partner_user_id, partner_device_id, partner_dev_key_id, partner_dev_key_sign,
                                       own_user_id, own_device_id, self.device_key, own_sign_key, ses)

        # MegOlm Session
        await self.api.send_megolm_pr_msg(self.room_id, partner_user_id, self.device_key, own_user_id, own_sign_key,
                                          partner_device_id, partner_dev_key_sign, partner_dev_key_id, ses, self.meg_ses)

        # Set this room to encrypted, forces messages to be sent encrypted
        self.is_encrypted = True

    async def get_room_encryption(self):
        """
        Yields room encryption events whenever they occur. Room encryption events set the room to now be in
        encrypted only mode.
        :return: Tuple of Room ID, Sender ID, and Algorithm
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("encryption", temp_queue, self.room_id)

        while True:
            try:
                room_id, sender, algorithm = await temp_queue.get()
                yield room_id, sender, algorithm
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("encryption", temp_queue, self.room_id)

    async def get_encrypted_message(self):
        """
        Yields encrypted message events whenever they occur.
        :return: Tuple of Room ID, sender ID, Ciphertext, Sender Device ID and MegOlm session ID
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("encrypted", temp_queue, self.room_id)

        while True:
            try:
                room_id, sender, ciphertext, device_id, session_id = await temp_queue.get()
                yield room_id, sender, ciphertext, device_id, session_id
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("encrypted", temp_queue, self.room_id)

    async def get_prekey_message(self):
        """
        Yields PreKey events whenever they occur. PreKey events indicate that a party wants to exchange
        encrypted information with us and initiate the setup of an secure channel.
        :return: Room_id, sender, content
        """
        temp_queue = asyncio.Queue()
        await self.event_manager.add_subscriber("prekey", temp_queue, self.room_id)

        while True:
            try:
                room_id, sender, content = await temp_queue.get()
                yield room_id, sender, content
            except asyncio.CancelledError:
                await self.event_manager.remove_subscriber("prekey", temp_queue, self.room_id)

    async def wait_room_encryption(self):
        """
        Coroutine task, waits for m.room.encryption events to occur and reacts accordingly:
        sets encryption of the room and starts the internal corouting tasks to receive prekey and encrypted messages
        """
        async for message in self.get_room_encryption():
            logging.debug("Received m.room.encryption for this room: \"%s\"", message[0])
            if message[2] == self.session.get_supported_encryption_version():
                self.is_encrypted = True
                if not self.prekey_task and not self.encrypted_task:
                    loop = asyncio.get_event_loop()
                    self.prekey_task = loop.create_task(self.wait_olm_megolm_prekey())
                    self.encrypted_task = loop.create_task(self.wait_enc_message())
            else:
                raise AiomatrixError('Received room encryption request with unsupported/wrong algorithm. '
                                     'Received: {0} Expected: {1}'.format(message[2],
                                                                          self.session.get_supported_encryption_version()))

    async def wait_olm_megolm_prekey(self):
        """
        Waits for an PreKey event. If it occurs the OlmSession is setup and saved, the MegOlm session is extracted
        and added into the local dict to be used for decrypting m.room.encrypted message events
        from this sender.
        """
        async for message in self.get_prekey_message():
            logging.debug("Received m.room.encrypted PreKey message")

            sender_id = message[1]
            content = message[2]

            sender_key = content['sender_key']

            # Get olm/megolm prekey message (both in one) by taking the part containing your own device_key
            if content['ciphertext'][self.session.get_device_key()]['type'] == 0:

                # New prekey message to establish new olm session
                initial_message = olm.session.OlmPreKeyMessage(content['ciphertext'][self.session.get_device_key()]['body'])
                olm_ses = olm.InboundSession(self.olm_account, initial_message)

                self.session.set_olm_session(sender_id, sender_key, olm_ses)
            else:

                # Uses already established olm session, stored in session class because used accross rooms
                initial_message = olm.session.OlmMessage(content['ciphertext'][self.session.get_device_key()]['body'])

                olm_ses = self.session.get_olm_session(sender_id, sender_key)

            dec_init_msg = olm_ses.decrypt(initial_message)
            msg = json.loads(dec_init_msg)

            # TODO what to do with room ID? This message is to_device and not room_id dependent
            # TODO resulting in EVERY room, listening for preKey events will receive this message and
            # TODO only after decrypting realize that it's not for this room
            room_id = msg['content']['room_id']
            if room_id != self.room_id:
                return

            ses_key = msg['content']['session_key']
            sender_device_id = msg['sender_device']
            session_id = msg['content']['session_id']

            self.set_room_key(sender_id, sender_device_id, session_id, olm.InboundGroupSession(ses_key))

            logging.debug('Received and stored olm/megolm session for: \"%s\", \"%s\"', sender_id, sender_device_id)

    async def wait_enc_message(self):
        """
        Waits for an encrypted message to be received. Get's the stored MegOlm session, decrypts the message
        and puts the decrypted message back into the event loop.
        """
        async for message in self.get_encrypted_message():
            logging.debug("Received m.room.encrypted message for this room: \"%s\"", message[0])
            sender_device_id = message[3]
            session_id = message[4]

            meg_ses = self.room_keys.get((message[1], sender_device_id, session_id))

            # If the megolm session is not yet available (can happen if m.room.encrypted is handled faster than prekey)
            if not meg_ses:
                await asyncio.sleep(5)
                meg_ses = self.room_keys.get((message[1], sender_device_id, session_id))

            if meg_ses:
                dec_msg = meg_ses.decrypt(message[2])
                msg_json = json.loads(dec_msg[0])
                msg = msg_json['content']['body']

                # Put message decrypted in queue for room to receive
                (self.event_manager.get_general_queue()).put_nowait(("message", message[0], message[1], msg))

    # endregion
