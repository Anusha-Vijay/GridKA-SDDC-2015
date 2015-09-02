#!/usr/bin/env python
import sys
import logging
import uuid
import signal

from mesos.interface import Scheduler, mesos_pb2
from mesos.native import MesosSchedulerDriver
import time

logging.basicConfig(level=logging.INFO)
TASK_CPUS = 0.1
TASK_MEM = 256
RUNNING_TASKS = 5


def new_task(offer):
    task = mesos_pb2.TaskInfo()
    task.task_id.value = str(uuid.uuid4())
    task.slave_id.value = offer.slave_id.value
    task.name = "HelloWorld"

    cpus = task.resources.add()
    cpus.name = "cpus"
    cpus.type = mesos_pb2.Value.SCALAR
    cpus.scalar.value = TASK_CPUS

    mem = task.resources.add()
    mem.name = "mem"
    mem.type = mesos_pb2.Value.SCALAR
    mem.scalar.value = TASK_MEM

    return task


def max_tasks_to_run_with_offer( offer):
    logging.info("CPUs: %s MEM: %s",
                 offer.resources[0].scalar.value,
                 offer.resources[1].scalar.value)

    cpu_tasks = int(offer.resources[0].scalar.value/TASK_CPUS)
    mem_tasks = int(offer.resources[1].scalar.value/TASK_MEM)

    return cpu_tasks if cpu_tasks <= mem_tasks else mem_tasks


def shutdown(signal, frame):
    logging.info("Shutdown signal")
    driver.stop()
    time.sleep(5)
    sys.exit(0)


class HelloWorldScheduler(Scheduler):
    def __init__(self):
        self.runningTasks = 0

    def registered(self, driver, framework_id, master_info):
        logging.info("Registered with framework id: %s on: %s", framework_id, master_info.hostname)

    def resourceOffers(self, driver, offers):
        logging.info("Recieved resource offers: %s",
                     [o.id.value for o in offers])
        tasks_to_start = RUNNING_TASKS - self.runningTasks
        for offer in offers:
            if RUNNING_TASKS <= self.runningTasks:
                driver.declineOffer(offer.id)
                return
            count_tasks = max_tasks_to_run_with_offer(offer)
            start_tasks = count_tasks if count_tasks <= tasks_to_start else tasks_to_start
            tasks_to_start -= start_tasks

            if start_tasks <= 0:
                logging.info("Decline Offer %s", offer.id)
                driver.declineOffer(offer.id)
                return

            logging.info("Start %s tasks", start_tasks)
            tasks = []
            for i in range(start_tasks):
                task = new_task(offer)
                task.command.value = "while [ true ]; do echo hello world && sleep 1 ; done"
                logging.info("Added task %s "
                             "using offer %s.",
                             task.task_id.value,
                             offer.id.value)
                tasks.append(task)
            logging.info("Launch %s Tasks", len(tasks))
            driver.launchTasks(offer.id, tasks)

    def statusUpdate(self, driver, update):
        '''
        when a task is started, over,
        killed or lost (slave crash, ....), this method
        will be triggered with a status message.
        '''
        logging.info("Task %s is in state %s" %
                     (update.task_id.value,
                      mesos_pb2.TaskState.Name(update.state)))

        if update.state == mesos_pb2.TASK_RUNNING:
            self.runningTasks += 1
            logging.info("Running tasks: %s", self.runningTasks)
            return

        if update.state != mesos_pb2.TASK_RUNNING or\
           update.state != mesos_pb2.TASK_STARTING or\
           update.state != mesos_pb2.TASK_STAGING:
            self.runningTasks -= 1
            logging.info("Running tasks: %s", self.runningTasks)

if __name__ == '__main__':
    framework = mesos_pb2.FrameworkInfo()
    framework.user = ""  # Have Mesos fill in the current user.
    framework.name = "hello-world"
    helloWorldScheduler = HelloWorldScheduler()
    driver = MesosSchedulerDriver(
        helloWorldScheduler,
        framework,
        "zk://localhost:2181/mesos"  # assumes running on the master
    )
    driver.start()
    logging.info("Listening for Ctrl-C")
    signal.signal(signal.SIGINT, shutdown)
    while True:
        time.sleep(5)
