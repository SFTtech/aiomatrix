import asyncio
import olm
import logging


from .api import client
from aiomatrix.errors import AiomatrixError


class Room:
    """Instance of a matrix room"""
    def __init__(self, session, api, event_manager, room_id, room_alias=None):
        self.session = session
        self.api = api
        self.room_id = room_id
        self.room_alias = room_alias
        self.event_manager = event_manager

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
        #TODO if encryption activated use self.api.send_enc()
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
        #await self.api.encrypt_room(self.room_id)
        #TODO get members of room, for loop over members, save megsessions in a list
        await self.__create_room_encryption()

    async def __create_room_encryption(self):
        partner_user_id = "@ebnera:in.tum.de"
        self_user_id = "@fuhhbarmatrixtest:matrix.org"
        partner_device_id = 'YPWKTLRKZG'
        self_device_id = 'HWWBTMCIEJ'
        room_id = "!RThAGWptqQbhWfJmzs:in.tum.de"

        ###################################### Own account

        # save acc and only load if not saved before to make sure to use the same keys every time
        pick_path = '/home/andi/devel/matrix/tmp/kartoffel'

        '''acc = olm.Account()
        p = acc.pickle("kartoffel")
        f = open(pick_path, 'wb+')
        f.write(p)
        f.close()'''

        with open(pick_path, 'rb') as f:
            pick = f.read()
            acc = olm.Account.from_pickle(pick, "kartoffel")

        self_device_key = acc.identity_keys["curve25519"]

        # You can only upload new keys when the old are read (?!)
        # TODO: wtf? why
        print(await self.api.keys_query(self_user_id))
        print(await self.api.keys_claim(self_user_id, self_device_id))

        # await self.keys_upload(acc, self_name, self_device_id)
        self_otk = await self.api.otk_upload(acc, self_user_id, self_device_id)

        ############################### Partner Identity Keys

        kquery = await self.api.keys_query(partner_user_id)

        if partner_device_id in list(kquery['device_keys'][partner_user_id].keys()):
            device_id = partner_device_id
        else:
            raise AiomatrixError("Unknown device " + partner_device_id + ". Cannot query required device keys.")

        dev_key_id = kquery['device_keys'][partner_user_id][device_id]['keys']['curve25519:' + device_id]
        dev_key_sign = kquery['device_keys'][partner_user_id][device_id]['keys']['ed25519:' + device_id]
        signature = kquery['device_keys'][partner_user_id][device_id]['signatures'][partner_user_id][
            'ed25519:' + device_id]

        logging.debug("Identity keys info for \"%s\": \"%s\" \"%s\" \"%s\"", device_id, dev_key_id, dev_key_sign,
                      signature)

        keys_json = kquery['device_keys'][partner_user_id][device_id]
        del keys_json['signatures']
        del keys_json['unsigned']

        olm.ed25519_verify(dev_key_sign, client.lowlevel.AioMatrixApi.canonical_json(keys_json), signature)

        ############################ Partner One-Time Key

        kclaim = await self.api.keys_claim(partner_user_id, device_id)

        key_description = list(kclaim['one_time_keys'][partner_user_id][partner_device_id].keys())[0]
        otk = kclaim['one_time_keys'][partner_user_id][partner_device_id][key_description]['key']
        otk_signature = \
        kclaim['one_time_keys'][partner_user_id][partner_device_id][key_description]['signatures'][partner_user_id][
            'ed25519:' + partner_device_id]

        logging.debug("OTK key info for \"%s\": \"%s\" \"%s\"", device_id, otk, otk_signature)

        otk_json = {'key': otk}

        olm.ed25519_verify(dev_key_sign, client.lowlevel.AioMatrixApi.canonical_json(otk_json), otk_signature)

        ####################### Olm Session

        ses = olm.OutboundSession(acc, dev_key_id, otk)

        # create olm m.encrypted
        await self.api.send_olm_pr_msg(partner_user_id, partner_device_id, dev_key_id, dev_key_sign, self_user_id,
                                   self_device_id, self_device_key, self_otk, ses)

        ######################## MegOlm Session

        megses = olm.OutboundGroupSession()

        await self.api.send_megolm_pr_msg(room_id, partner_user_id, self_device_key, self_user_id, self_otk,
                                      partner_device_id, dev_key_sign, dev_key_id, ses, megses)

        ######################## Send encrypted to room

        msg = "oh hahaha"

        await self.api.send_enc(room_id, self_device_id, self_device_key, megses, msg)

    # endregion
