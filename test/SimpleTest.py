from aiomatrix.session import Session
import asyncio


def on_receive(room, sender, message):
    print(room, sender, message)


async def main():
    ses = Session("fuhhbarmatrixtest", "monkey", "https://matrix.org", log_level=20)
    async with ses:
    #async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org") as ses:

        await ses.connect()

        room = await ses.room_join("#fuhhbar:in.tum.de")

        await room.send_message("aioTestMessage")

        await room.add_listener_receive_messages(on_receive)

        #await room.del_listener_receive_messages(on_receive)
        #or
        #await room.del_listener_receive_messages()

        while True:
            await asyncio.sleep(20)
            await room.send_message("randomMsg")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())