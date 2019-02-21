from aiomatrix.session import Session
import asyncio


async def main():
    async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org", "HWWBTMCIEJ", log_level=10) as ses:

        await ses.connect()

        room = await ses.room_join("!RThAGWptqQbhWfJmzs:in.tum.de")


        #await room.send_message("encTestMessage")

        await room.activate_encryption()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
