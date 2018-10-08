from aiomatrix.session import Session
import asyncio
import time


async def readm(room):
    async for message in room.get_new_message():
        print(message)

async def readt(room):
    async for message in room.get_typing():
        print(message)

async def readi(ses):
    async for message in ses.get_invite():
        print(message)


async def main():
    async with Session("fuhhbarmatrixroomtest", "monkey", "https://matrix.org") as ses2:
        await ses2.connect()

        async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org") as ses:

            await ses.connect()

            room = await ses.room_join("#fuhhbar:in.tum.de")

            await room.send_message("aioTestMessage")

            loop = asyncio.get_event_loop()
            task = loop.create_task(readm(room))
            loop.create_task(readt(room))
            loop.create_task(readi(ses))

            await asyncio.sleep(10)

            s = str(int(round(time.time() * 1000)))
            await ses2.room_create("testingroomformatrix15" + s, "test " + s,
                                   ["@ebnera:in.tum.de", "@fuhhbarmatrixtest:matrix.org"])

            await asyncio.sleep(5)
            await room.send_message("randomMsg1")
            await asyncio.sleep(5)
            await room.send_message("randomMsg2")
            await asyncio.sleep(5)
            await room.send_message("randomMsg3")
            await asyncio.sleep(5)


            task.cancel()

            while True:
                await asyncio.sleep(20)
                await room.send_message("randomMsg")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())