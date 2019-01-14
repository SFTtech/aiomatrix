from aiomatrix.session import Session
import asyncio


async def main():
    async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org", "HWWBTMCIEJ") as ses:
    #async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org", "DWTYLSQHPH") as ses:

        await ses.connect()

        #room = await ses.room_join("!MbCSOfWuHCOEQGTWTf:in.tum.de")
        room = await ses.room_join("!KhBqCWMQcSJMeRLbrB:in.tum.de")
        print(room.room_id)


        #await room.send_message("encTestMessage")

        #await room.testEnc()

        await ses.testEnc()



loop = asyncio.get_event_loop()
loop.run_until_complete(main())