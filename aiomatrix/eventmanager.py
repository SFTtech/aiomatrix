import asyncio
import logging

from .api import client


class EventManager:
    """Manages the requesting and distribution of matrix events."""
    def __init__(self, api):
        self.api = api
        self.filter = client.filter.EventFilter()
        self.sync_task = None
        self.rec_task = None
        self.general_queue = asyncio.Queue()

        self.subscriber_list = {
            'message': list(),
            'typing':list(),
            'invite':list()
        }

    async def cancel(self):
        """
        Cancels all internal tasks.
        """
        self.sync_task.cancel()
        self.rec_task.cancel()

    async def start(self):
        """
        Starts the internal tasks to receive and distribute matrix events.
        """
        loop = asyncio.get_event_loop()
        self.rec_task = loop.create_task(self.__wait_general_event())
        self.sync_task = loop.create_task(self.__sync_task())

    async def add_subscriber(self, event, queue, room_id=None):
        """
        Adds a subscriber event queue to the required/acepted events list.
        The filter class takes care of adjusting the sync filter and parsing the results.
        :param event: Event type, e.g. "message", "typing", "invite", ...
        :param queue: Queue the received event content is put in.
        :param room_id: Room Id, has to be passed for room specific events.
        """
        self.subscriber_list[event].append((room_id, queue))
        self.filter.set_filter(event, room_id)

        if len(self.subscriber_list[event]) == 1:
            # restart queue, cause new event
            await self.__restart_tasks()

    async def remove_subscriber(self, event, queue, room_id=None):
        """
        Removes a subscriber event queue from the required/accepted events.
        The filter class handles the correct adjustment of the sync filter.
        :param event: Event type, e.g. "message", "typing", "invite", ...
        :param queue: Queue the received event content is put in.
        :param room_id: Room Id, has to be passed for room specific events.
        """
        self.subscriber_list[event].remove((room_id, queue))
        self.filter.remove_filter(event, room_id)

        if not self.subscriber_list[event]:
            # Restart queue, cause one type of event is no longer required
            await self.__restart_tasks()

            # Cancel tasks if all empty
            for event_type in self.subscriber_list:
                if self.subscriber_list[event_type]:
                    return
            self.cancel()

    async def __sync_task(self):
        """
        Calls the lowlevel sync method with a filter depending on the awaited events/queues.
        Fills the general event queue with the parsed responses.
        """
        if not self.api.get_since_token():
            # Remove old events (set since_token to now), not when events/filter change
            resp_json = await self.api.sync()
            self.api.set_since_token(resp_json["next_batch"])

        # Start waiting for new events
        while True:
            resp_json = await self.api.sync(self.filter.get_filter_string())
            self.api.set_since_token(resp_json["next_batch"])

            event_resp = self.filter.get_filtered_event(resp_json)
            if event_resp:
                self.general_queue.put_nowait(event_resp)

    async def __wait_general_event(self):
        """
        General event loop. Waits for accepted events and distributes
        them into the corresponding consumer queues.
        """
        while True:
            event = await self.general_queue.get()
            if "message" in event[0]:
                for room, subscriber in self.subscriber_list['message']:
                    if event[1] == room:
                        # remove event type string and put in subscribers queues
                        subscriber.put_nowait(event[1:])
            elif "typing" in event[0]:
                for room, subscriber in self.subscriber_list['typing']:
                    if event[1] == room:
                        # remove event type string and put in subscribers queues
                        subscriber.put_nowait(event[1:])
            elif "invite" in event[0]:
                for _room, subscriber in self.subscriber_list['invite']:
                    # remove event type string and put in subscribers queues
                    subscriber.put_nowait(event[1:])
            else:
                logging.warning("Unknown event received: %s", event[0])

    async def __restart_tasks(self):
        if self.sync_task:
            self.sync_task.cancel()
        await self.start()
