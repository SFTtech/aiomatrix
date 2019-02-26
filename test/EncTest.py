from aiomatrix.session import Session
import asyncio


async def main():
    async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org", "HWWBTMCIEJ", log_level=10) as ses:

        await ses.connect()

        room = await ses.room_join("!RThAGWptqQbhWfJmzs:in.tum.de")

        await room.activate_encryption()

        await room.send_message("lal ah")

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
