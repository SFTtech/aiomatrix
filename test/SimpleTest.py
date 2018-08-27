from aiomatrix.session import Session
import asyncio


def on_receive(room, sender, message):
    print(room, sender, message)
'''def on_receipt(room, sender, message):
    print(room, sender, message)
def on_typing(room, sender):
    print(room, sender, 'typing')'''


async def main():
    async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org") as ses:

        await ses.connect()

        room = await ses.room_join("#fuhhbar:in.tum.de")

        await room.send_message("aioTestMessage")

        await room.add_listener_receive_messages(on_receive)
        #await room.add_listener_receipt(on_receipt)
        #await room.add_listener_typing(on_typing)

        await room.del_listener_receive_messages(on_receive)
        #await room.del_listener_receipt(on_receipt)
        #await room.del_listener_typing(on_typing)

        '''async for message in room.get_new_message():
            print(message)'''

        while True:
            await asyncio.sleep(20)
            await room.send_message("randomMsg")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())