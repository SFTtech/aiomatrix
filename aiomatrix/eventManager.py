import asyncio

from .api import client

class EventManager():
    def __init__(self, room_id, api):
        self.room_id = room_id
        self.api = api
        self.filter = client.filter.EventFilter()
        self.sync_task = None
        self.rec_task = None
        self.general_queue = asyncio.Queue()

        self.customer_list = {
            'message': list(),
            'typing':list(),
            'invite':list()
        }


    async def cancel(self):
        self.sync_task.cancel()

    async def start(self):
        loop = asyncio.get_event_loop()
        #TODO wait for event first or start getting events first? Order
        self.sync_task = loop.create_task(self.__sync_task())
        self.rec_task = loop.create_task(self.__wait_general_event())

    async def add_customer(self, event, queue):
        # TODO: check event is valid name (?)
        self.customer_list[event].append(queue)

        if len(self.customer_list[event]) == 1:
            # update filter
            if event is "message":
                self.filter.set_filter_message()
            if event is "typing":
                self.filter.set_filter_typing()

            # restart queue, cause new event
            await self.__restart_tasks()

    async def remove_customer(self, event, queue):
        self.customer_list[event].remove(queue)

        if not self.customer_list[event]:
            # update filter
            if event is "message":
                self.filter.set_filter_message(False)
            if event is "typing":
                self.filter.set_filter_typing(False)

            # Restart queue, cause one type of event is no longer required
            await self.__restart_tasks()

            # Cancel tasks if all empty
            for event_type in self.customer_list:
                if self.customer_list[event_type]:
                    return
            self.sync_task.cancel()
            self.rec_task.cancel()


    async def __sync_task(self):
        # Remove old events (set since_token to now)
        resp_json = await self.api.sync()
        self.api.set_since_token(resp_json["next_batch"])

        # Start waiting for new events
        while True:
            resp_json = await self.api.sync(self.filter.get_filter_string())
            self.api.set_since_token(resp_json["next_batch"])

            #TODO parsing of response with filter class
            if self.room_id in resp_json['rooms']['join']:
                for event in resp_json['rooms']['join'][self.room_id]['timeline']['events']:
                    self.general_queue.put_nowait(({"message"}, self.room_id, event['sender'], event['content']['body']))

            if self.room_id in resp_json['rooms']['join']:
                for event in resp_json['rooms']['join'][self.room_id]['ephemeral']['events']:
                    # The 'and' part is added, because when one stops typing you receive an empty 'm.typing' event
                    if 'user_ids' in event['content'] and event['content']['user_ids']:
                        self.general_queue.put_nowait(({"typing"}, self.room_id, event['content']['user_ids']))

            if resp_json['rooms']['invite']:
                for key in resp_json['rooms']['invite']:
                    for event in resp_json['rooms']['invite'][key]['invite_state']['events']:
                        if 'name' in event['content']:
                            self.general_queue.put_nowait(({"invite"}, key, event['content']['name'], event['sender']))

    async def __wait_general_event(self):
        while True:
            event = await self.general_queue.get()
            # TODO: correctly switch events
            if "message" in event[0]:
                for customer in self.customer_list['message']:
                    # remove event type string and put in customers queues
                    customer.put_nowait(event[1:])
            elif "typing" in event[0]:
                for customer in self.customer_list['typing']:
                    # remove event type string and put in customers queues
                    customer.put_nowait(event[1:])
            elif "invite" in event[0]:
                for customer in self.customer_list['invite']:
                    # remove event type string and put in customers queues
                    customer.put_nowait(event[1:])
            else:
                print("unknown event received")

    async def __restart_tasks(self):
        if self.sync_task:
            self.sync_task.cancel()
        await self.start()
