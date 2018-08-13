from aiomatrix.session import Session
import asyncio


async def main():
    #ses = Session(user="@JJ:server.org", password="asdfasdf")
    #ses = Session(username="fuhhbarmatrixtest", password="monkey", base_url="https://matrix.org")
    ses = Session("@fuhhbarmatrixtest:matrix.org", "monkey")

    await ses.connect()

    room = await ses.room_join("#fuhhbar:in.tum.de")

    '''i = 0
    while True:
        await room.send_message("%d" % i)
        i += 1
        await asyncio.sleep(60)'''

    await room.send_message("aioTestMessage")

    await ses.disconnect()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())