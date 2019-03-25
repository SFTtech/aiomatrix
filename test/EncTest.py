from aiomatrix.session import Session
import asyncio


async def read_message(room):
    async for message in room.get_message():
        print("Room message: ", message)


async def read_invite(ses):
    async for message in ses.get_invite():
        room = await ses.room_join(message[0])
        return room


async def read_otk(ses):
    async for message in ses.get_otk_count():
        print("OTK count: ", message)


async def main():
    # Create session
    async with Session("fuhhbarmatrixtest", "monkey", "https://matrix.org", "HWWBTMCIEJ",
                       log_level=10, save_directory_path='/home/andi/devel/matrix/tmp/') as ses:

        await ses.connect()

        async_loop = asyncio.get_event_loop()
        async_loop.create_task(read_otk(ses))
        room = await ses.room_join("!YhjtGXjrGkVwrajgcd:in.tum.de")
        #room = await loop.create_task(read_invite(ses))
        async_loop.create_task(read_message(room))

        '''

        # Join/Create room(s)
        room = await ses.room_create("Test Show Room", ["@ebnera:in.tum.de"])

        # Wait for accept
        await asyncio.sleep(30)

        # Register for room messages
        async_loop = asyncio.get_event_loop()
        recv_msg = async_loop.create_task(read_message(room))

        await room.send_message("non-encrypted message")

        # API initiates encryption
        await room.activate_encryption()

        await room.send_message("encrypted message")

        await recv_msg
        
        '''

        while True:
            #room.pickle_room_keys()
            await asyncio.sleep(20)
            await room.send_message("encrypted message")

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
